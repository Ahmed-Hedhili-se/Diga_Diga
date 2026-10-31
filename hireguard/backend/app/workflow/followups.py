"""Candidate follow-ups (spec: "reminders prepared for candidates who have not answered").

Code finds candidates we wrote to (email_outbox, i.e. an approved and executed email) who have not written
back (inbox_items matched to their verified address) for N business days, and drafts a templated reminder
into the approval queue. Nothing is sent here. At most MAX_REMINDERS per candidate, so nobody is chased
forever, and a candidate with a reminder still waiting for approval is not drafted twice.
"""
import sqlite3
from datetime import date, datetime, timedelta, timezone

from ..contracts import ApprovalItem, ApprovalKind
from ..db import connect, tx
from . import approvals, templates
from .common import new_id, now
from .drafting import COMPANY, RECRUITER, STATUS_LABELS, job_title

DEFAULT_DAYS = 3
MAX_REMINDERS = 2


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
