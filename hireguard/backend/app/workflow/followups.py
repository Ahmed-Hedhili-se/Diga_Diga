"""Candidate follow-ups: reminders drafted into the approval queue, never sent here.

Two implementations met in the merge of `main` and `yasmina` and both are kept, because each has its own routes,
UI and tests. TODO(Hedhili, Ahmed): consolidate into one.
  - preview()/run() (P3, Hedhili): a candidate is "silent" when our last executed email to their verified address is
    older than N days and no verified inbound email came after it; closed candidates (rejected, hired, withdrawn)
    are skipped; spoofed mail counts neither as a reply nor as a language signal. Used by /followups/preview|run.
  - awaiting_reply()/draft() (Ahmed): N business days without a reply, at most MAX_REMINDERS per candidate, no
    duplicate while one waits for approval. Used by /followups and /followups/draft.
Both read only our own tables and fill templates with DB slots, so no inbound email text can reach a reminder.
"""
import sqlite3
from datetime import date, datetime, timedelta, timezone

from ..contracts import ApprovalItem, ApprovalKind, UserOut
from ..db import connect, tx
from . import approvals, audit, drafting, templates
from .common import new_id, now, table_exists
from .drafting import COMPANY, RECRUITER, STATUS_LABELS, job_title

TEMPLATE = "followup_reminder"
CLOSED_STATUSES = {"rejected", "hired", "withdrawn"}
MAX_REMINDERS = 2  # per candidate, ever (executed ones); after that a human follows up


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _effective_status(conn, cid: str, fallback: str | None) -> str | None:
    """Latest executed status change for the candidate wins over P1's intake status."""
    r = conn.execute("SELECT status_to FROM workflow_status_changes WHERE object_type='candidate' AND object_id=? "
                     "ORDER BY at DESC LIMIT 1", (cid,)).fetchone()
    return r["status_to"] if r else fallback


def _last_outbound(conn, cid: str, addr: str):
    return conn.execute(
        "SELECT o.sent_at, o.lang FROM email_outbox o JOIN approval_items a ON a.id = o.approval_item_id "
        "WHERE json_extract(a.payload, '$.candidate_id') = ? AND lower(o.to_addr) = ? "
        "ORDER BY o.sent_at DESC LIMIT 1", (cid, addr.lower())).fetchone()


def _verified_inbound(conn, cid: str, addr: str) -> list:
    """Inbound emails the gate linked to this candidate (never the suspicious lane), newest first."""
    return conn.execute(
        "SELECT received_at, language FROM inbox_items WHERE candidate_id = ? AND lower(from_addr) = ? "
        "AND lane != 'suspicious' ORDER BY received_at DESC", (cid, addr.lower())).fetchall()


def _reminder_blocked(conn, cid: str, cutoff: datetime) -> bool:
    """No duplicates: a reminder is waiting or was drafted recently, or the cap is reached."""
    rows = conn.execute(
        "SELECT status, created_at FROM approval_items WHERE kind = 'email_send' AND is_canary = 0 "
        "AND json_extract(payload, '$.template') = ? AND json_extract(payload, '$.candidate_id') = ?",
        (TEMPLATE, cid)).fetchall()
    if any(r["status"] in ("pending", "approved") or _ts(r["created_at"]) >= cutoff for r in rows):
        return True
    return sum(r["status"] == "executed" for r in rows) >= MAX_REMINDERS


def find_silent_candidates(conn: sqlite3.Connection, days: int = 3, today: datetime | None = None) -> list[dict]:
    if not table_exists(conn, "candidates"):
        return []
    cutoff = (today or now()) - timedelta(days=days)
    out = []
    for c in conn.execute("SELECT * FROM candidates ORDER BY candidate_id").fetchall():
        c = dict(c)
        cid, addr = c["candidate_id"], c.get("email") or ""
        if not addr or _effective_status(conn, cid, c.get("status")) in CLOSED_STATUSES:
            continue
        sent = _last_outbound(conn, cid, addr)
        if sent is None or _ts(sent["sent_at"]) >= cutoff:
            continue
        inbound = _verified_inbound(conn, cid, addr)
        if any(_ts(m["received_at"]) > _ts(sent["sent_at"]) for m in inbound):
            continue
        if _reminder_blocked(conn, cid, cutoff):
            continue
        lang = next((m["language"] for m in inbound if m["language"]), None) or sent["lang"]
        out.append({"candidate_id": cid, "name": c.get("name") or "", "email": addr, "job_id": c.get("job_id") or "",
                    "lang": drafting._lang(lang or "fr"), "last_sent_at": sent["sent_at"],
                    "days_silent": ((today or now()) - _ts(sent["sent_at"])).days})
    return out


def _draft_one(conn, cand: dict, created_by: str) -> str:
    slots = {"candidate_name": cand["name"], "job_title": drafting.job_title(conn, cand["job_id"]),
             "recruiter_name": drafting.RECRUITER["name"], "company_name": drafting.COMPANY}
    subject, body = templates.render("email", TEMPLATE, cand["lang"], slots)
    item = approvals.create_item(
        ApprovalKind.email_send, f"Follow-up reminder to {cand['candidate_id']}",
        {"template": TEMPLATE, "candidate_id": cand["candidate_id"], "to": cand["email"], "recipient_verified": True,
         "subject": subject, "body": body, "lang": cand["lang"]},
        created_by, diff={"before": None, "after": {"to": cand["email"], "subject": subject}}, conn=conn)
    return item.id


def draft_reminders(conn: sqlite3.Connection | None = None, days: int = 3, today: datetime | None = None,
                    user: UserOut | None = None) -> list[str]:
    """One `email_send` approval item per silent candidate. Returns the created (real, non-canary) item ids."""
    if conn is None:
        with tx() as c:
            return draft_reminders(c, days, today, user)
    created = [_draft_one(conn, cand, "system") for cand in find_silent_candidates(conn, days, today)]
    audit.append(user.id if user else "system", "followups.run", "followups", (today or now()).date().isoformat(),
                 {"days": days, "created": len(created), "item_ids": created}, conn=conn)
    return created


def preview(days: int = 3) -> list[dict]:
    conn = connect()
    try:
        return [{k: c[k] for k in ("candidate_id", "job_id", "lang", "last_sent_at", "days_silent")}
                for c in find_silent_candidates(conn, days, now())]
    finally:
        conn.close()


def run(user: UserOut, days: int = 3) -> dict:
    return {"item_ids": draft_reminders(days=days, today=now(), user=user)}

# ---------------------------------------------------------------- business-day reminders (Ahmed)

DEFAULT_DAYS = 3


def business_days(start: date, end: date) -> int:
    """Weekdays strictly after `start`, up to and including `end`."""
    n, d = 0, start
    while d < end:
        d += timedelta(days=1)
        n += d.weekday() < 5
    return n


def _reminders(conn: sqlite3.Connection, candidate_id: str) -> tuple[int, bool]:
    rows = conn.execute(
        "SELECT status FROM approval_items WHERE is_canary = 0 AND status != 'rejected' "
        "AND json_extract(payload, '$.followup') = 1 AND json_extract(payload, '$.candidate_id') = ?",
        (candidate_id,)).fetchall()
    return len(rows), any(r["status"] in ("pending", "approved") for r in rows)


def awaiting_reply(days: int = DEFAULT_DAYS, today: date | None = None,
                   conn: sqlite3.Connection | None = None) -> list[dict]:
    own = conn is None
    conn = conn or connect()
    today = today or now().date()
    try:
        rows = conn.execute(
            "SELECT c.candidate_id, c.name, c.email, c.job_id, o.sent_at, o.subject, o.lang "
            "FROM candidates c JOIN email_outbox o ON lower(o.to_addr) = lower(c.email) "
            "WHERE o.sent_at = (SELECT MAX(sent_at) FROM email_outbox WHERE lower(to_addr) = lower(c.email))"
        ).fetchall()
        out = []
        for r in rows:
            sent = datetime.fromisoformat(r["sent_at"]).date()
            replied = conn.execute("SELECT 1 FROM inbox_items WHERE candidate_id = ? AND received_at > ?",
                                   (r["candidate_id"], r["sent_at"])).fetchone()
            waited = business_days(sent, today)
            sent_count, pending = _reminders(conn, r["candidate_id"])
            if replied or waited < days:
                continue
            out.append({"candidate_id": r["candidate_id"], "name": r["name"], "job_id": r["job_id"],
                        "last_sent_at": r["sent_at"], "last_subject": r["subject"], "lang": r["lang"],
                        "business_days_waiting": waited, "reminders_sent": sent_count,
                        "reminder_pending": pending, "can_remind": sent_count < MAX_REMINDERS and not pending})
        return sorted(out, key=lambda x: -x["business_days_waiting"])
    finally:
        if own:
            conn.close()


def draft(candidate_ids: list[str], actor: str, days: int = DEFAULT_DAYS) -> list[ApprovalItem]:
    out = []
    with tx() as conn:
        due = {x["candidate_id"]: x for x in awaiting_reply(days, conn=conn) if x["can_remind"]}
        for cid in candidate_ids:
            x = due.get(cid)
            if x is None:
                continue  # replied, not due yet, already reminded twice, or a reminder is waiting
            to = conn.execute("SELECT email FROM candidates WHERE candidate_id = ?", (cid,)).fetchone()["email"]
            lang = x["lang"] if x["lang"] in ("fr", "en", "ar") else "fr"
            subject, body = templates.render("email", "follow_up", lang, {
                "candidate_name": x["name"], "job_title": job_title(conn, x["job_id"]),
                "sent_date": x["last_sent_at"][:10], "recruiter_name": RECRUITER["name"], "company_name": COMPANY})
            out.append(approvals.create_item(
                ApprovalKind.email_send, f"Follow-up {x['reminders_sent'] + 1}/{MAX_REMINDERS} to {cid}",
                {"to": to, "subject": subject, "body": body, "lang": lang, "candidate_id": cid,
                 "recipient_verified": True, "followup": True, "reminder_no": x["reminders_sent"] + 1},
                actor, diff={"before": None, "after": {"to": to, "subject": subject}}, conn=conn))
    return out

# ---------------------------------------------------------------- demo seed (fictional)


SEED_APPLICANTS = {"JOB-FS-02": ("CAND-F", 6), "JOB-HR-03": ("CAND-H", 5)}
SEED_SILENT = {"CAND-F001": 8, "CAND-F002": 5, "CAND-H001": 6, "CAND-F003": 1}  # days since our email


def seed_history():
    """Fictional applicants for the two other open roles, and status emails 'sent' days ago to some of
    them who never answered (the CAND-00x demo candidates all wrote in today, so none of them is due).
    The emails are marked approval_item_id = 'seed:history' so they are never mistaken for executed approvals."""
    from ..scoring.rediscover import fictional_cvs, seed_cv  # P2's seeding helper

    for job_id, (prefix, n) in SEED_APPLICANTS.items():
        for i, gt in enumerate(fictional_cvs(job_id, n), start=1):
            seed_cv(gt, f"{prefix}{i:03d}", job_id)
    with tx() as conn:
        for cid, ago in SEED_SILENT.items():
            c = conn.execute("SELECT name, email, job_id FROM candidates WHERE candidate_id = ?", (cid,)).fetchone()
            if not c:
                continue
            subject, body = templates.render("email", "status_update", "fr", {
                "candidate_name": c["name"], "job_title": job_title(conn, c["job_id"]),
                "status_label": STATUS_LABELS["fr"]["under_review"], "recruiter_name": RECRUITER["name"],
                "company_name": COMPANY})
            sent = (datetime.now(timezone.utc) - timedelta(days=ago)).isoformat()
            conn.execute("INSERT INTO email_outbox VALUES (?,?,?,?,?,?,?)",
                         (new_id("OUT"), "seed:history", c["email"], subject, body, "fr", sent))
