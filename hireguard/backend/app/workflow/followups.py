"""Candidate follow-up reminders: drafted into the approval queue, never sent here.

A candidate is "silent" when we sent them an email (executed, to their verified address) more than N days ago
and no verified inbound email from them arrived after it. Reads only our own tables: the reminder is a template
with DB slots, so no text from any inbound email can reach it. Spoofed (suspicious) inbound mail counts neither
as a reply nor as a language signal.
"""
import sqlite3
from datetime import datetime, timedelta

from ..contracts import ApprovalKind, UserOut
from ..db import connect, tx
from . import approvals, audit, drafting, templates
from .common import now, table_exists

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
