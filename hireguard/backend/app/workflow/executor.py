"""The only code path that acts. It runs approved items only. Anything else gets HTTP 403, and the refusal is audited.

Other layers add handlers with `register_handler(kind, fn)`, where `fn(payload, conn) -> dict` runs inside the
executor's transaction (so the action, the status flip and the audit entry commit together).
"""
import json
import sqlite3
from typing import Any, Callable

from fastapi import HTTPException

from ..contracts import ApprovalKind, ApprovalStatus, UserOut
from ..db import register_schema, tx
from . import approvals, audit
from .common import canonical_json, new_id, now_iso

Handler = Callable[[dict[str, Any], sqlite3.Connection], dict[str, Any]]
_handlers: dict[ApprovalKind, Handler] = {}


def register_handler(kind: ApprovalKind | str, fn: Handler):
    _handlers[ApprovalKind(kind)] = fn
    return fn


@register_schema
def _schema(conn: sqlite3.Connection):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS email_outbox (
            id TEXT PRIMARY KEY,
            approval_item_id TEXT NOT NULL,
            to_addr TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            lang TEXT NOT NULL,
            sent_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS workflow_status_changes (
            approval_item_id TEXT PRIMARY KEY,
            object_type TEXT NOT NULL,
            object_id TEXT NOT NULL,
            status_from TEXT,
            status_to TEXT NOT NULL,
            at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS workflow_shortlists (
            approval_item_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            candidate_ids TEXT NOT NULL,
            committed_at TEXT NOT NULL
        );
        """
    )


def run(item_id: str, user: UserOut) -> dict:
    refusal, result = None, None
    with tx() as conn:
        r = conn.execute("SELECT id, kind, status, payload FROM approval_items WHERE id = ?", (item_id,)).fetchone()
        if not r:
            raise HTTPException(404, "approval item not found")
        kind = ApprovalKind(r["kind"])
        if not approvals.can_decide(user, kind):
            refusal = {"kind": kind.value, "status": r["status"], "reason": "role_not_allowed"}
        elif r["status"] != ApprovalStatus.approved.value:
            refusal = {"kind": kind.value, "status": r["status"], "reason": "not_approved"}
        elif approvals.is_canary(item_id, conn):
            # a reviewer approved a planted canary: nothing runs and the item is withdrawn (committed on exit)
            conn.execute("UPDATE approval_items SET status = 'rejected' WHERE id = ?", (item_id,))
            audit.append(user.id, "executor.canary_blocked", "approval_item", item_id, {"kind": kind.value}, conn=conn)
        else:
            handler = _handlers.get(kind)
            if handler is None:
                raise HTTPException(501, f"no executor handler for {kind.value}")
            result = handler(json.loads(r["payload"]) | {"approval_item_id": item_id}, conn)
            conn.execute("UPDATE approval_items SET status = ? WHERE id = ?", (ApprovalStatus.executed.value, item_id))
            audit.append(user.id, "executor.run", "approval_item", item_id, {"kind": kind.value, "result": result}, conn=conn)

    if result is not None:
        _record_activity(kind)  # after commit: P2's counter must not share (or block on) our write transaction
        return {"executed": True, "item_id": item_id, "result": result}
    if refusal is None:
        raise HTTPException(403, "item was withdrawn: nothing was executed")
    audit.append(user.id, "executor.refused", "approval_item", item_id, refusal)
    raise HTTPException(403, "item is not approved: nothing was executed")


ACTIVITY_FOR_KIND = {
    ApprovalKind.email_send: "emails",
    ApprovalKind.interview_booking: "emails",
    ApprovalKind.offer: "emails",
    ApprovalKind.document_release: "documents",
}


def _record_activity(kind: ApprovalKind):
    """Feeds P2's money dashboard (hours saved). Best effort: never fails an executed action."""
    activity = ACTIVITY_FOR_KIND.get(kind)
    if activity is None:
        return
    try:
        from ..scoring.money import record_activity
        record_activity(activity)
    except Exception:
        pass

# ---------------------------------------------------------------- default (mock) handlers


def _send_email(payload: dict, conn: sqlite3.Connection) -> dict:
    out_id = new_id("OUT")
    conn.execute("INSERT INTO email_outbox VALUES (?,?,?,?,?,?,?)",
                 (out_id, payload.get("approval_item_id", ""), payload["to"], payload["subject"], payload["body"],
                  payload.get("lang", "fr"), now_iso()))
    return {"outbox_id": out_id, "to": payload["to"]}


def _book_interview(payload: dict, conn: sqlite3.Connection) -> dict:
    from . import interviews, mock_calendar
    slot = mock_calendar.book(conn, payload["slot_id"], payload["candidate_id"])
    interview_id = interviews.create_interview(conn, payload["candidate_id"], payload.get("job_id", ""),
                                               slot, payload.get("recruiter_id", "recruiter"))
    sent = _send_email(payload["email"] | {"approval_item_id": payload["approval_item_id"]}, conn) \
        if payload.get("email") else None
    return {"slot_id": slot["id"], "interview_id": interview_id, "invite": sent}


def _release_document(payload: dict, conn: sqlite3.Connection) -> dict:
    from . import documents
    return documents.release(conn, payload["document_id"])


def _status_change(payload: dict, conn: sqlite3.Connection) -> dict:
    conn.execute("INSERT INTO workflow_status_changes VALUES (?,?,?,?,?,?)",
                 (payload["approval_item_id"], payload["object_type"], payload["object_id"],
                  payload.get("status_from"), payload["status_to"], now_iso()))
    return {"object_id": payload["object_id"], "status_to": payload["status_to"]}


def _shortlist(payload: dict, conn: sqlite3.Connection) -> dict:
    conn.execute("INSERT INTO workflow_shortlists VALUES (?,?,?,?)",
                 (payload["approval_item_id"], payload["job_id"], canonical_json(payload["candidate_ids"]), now_iso()))
    # mark scores committed if P2's table exists (P2 can override this handler)
    try:
        q = ",".join("?" * len(payload["candidate_ids"]))
        conn.execute(f"UPDATE score_results SET status='committed' WHERE job_id=? AND candidate_id IN ({q})",
                     (payload["job_id"], *payload["candidate_ids"]))
    except sqlite3.OperationalError:
        pass
    return {"job_id": payload["job_id"], "committed": len(payload["candidate_ids"])}


def _release_held_email(payload: dict, conn: sqlite3.Connection) -> dict:
    conn.execute("UPDATE inbox_items SET status = 'released' WHERE id = ?", (payload["inbox_id"],))
    return {"inbox_id": payload["inbox_id"], "status": "released"}


def _leave_request(payload: dict, conn: sqlite3.Connection) -> dict:
    return _status_change({"approval_item_id": payload["approval_item_id"], "object_type": "leave_request",
                           "object_id": payload["leave_id"], "status_to": "approved"}, conn)


def _offer(payload: dict, conn: sqlite3.Connection) -> dict:
    return _send_email(payload["email"] | {"approval_item_id": payload["approval_item_id"]}, conn)


register_handler(ApprovalKind.email_send, _send_email)
register_handler(ApprovalKind.interview_booking, _book_interview)
register_handler(ApprovalKind.document_release, _release_document)
register_handler(ApprovalKind.status_change, _status_change)
register_handler(ApprovalKind.shortlist_commit, _shortlist)
register_handler(ApprovalKind.held_email_release, _release_held_email)
register_handler(ApprovalKind.leave_request, _leave_request)
register_handler(ApprovalKind.offer, _offer)
