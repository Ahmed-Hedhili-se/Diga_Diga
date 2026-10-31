"""Writes to Odoo. They exist only as executor handlers, so they run only for approved items.

Each wrapped handler runs the original (local) action first, then mirrors it to Odoo inside the same executor
transaction. Any Odoo failure raises HTTP 502: the local transaction rolls back and the item stays `approved`.
Nothing written to Odoo comes from a model: notes are fixed templates and every dynamic value is HTML-escaped.
"""
from __future__ import annotations

import html
import os
import sqlite3
from datetime import datetime
from functools import lru_cache
from typing import Any, Callable

from fastapi import HTTPException

from ..contracts import ApprovalKind
from ..workflow import executor, mock_calendar
from . import odoo_client, sync
from .odoo_client import OdooError

SEND_EMAIL = os.getenv("HG_ODOO_SEND_EMAIL", "0") == "1"

Mirror = Callable[[dict, sqlite3.Connection, dict], Any]

_installed = False
_original_free_slots = mock_calendar.free_slots


def _wrap(kind: ApprovalKind, mirror: Mirror):
    original = executor._handlers[kind]

    def handler(payload: dict, conn: sqlite3.Connection) -> dict:
        result = original(payload, conn)
        try:
            mirrored = mirror(payload, conn, result)
        except OdooError as e:
            raise HTTPException(502, f"ERP write failed, nothing was executed: {e}") from e
        return result | {"odoo": mirrored}

    executor.register_handler(kind, handler)


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _note(applicant_id: int, html_body: str):
    odoo_client.call("hr.applicant", "message_post", [applicant_id], body=html_body,
                     message_type="comment", subtype_xmlid="mail.mt_note")


def _linked_applicant(conn: sqlite3.Connection, payload: dict, email: dict | None = None) -> int | None:
    cid = payload.get("candidate_id")
    if not cid and email and email.get("to"):
        r = conn.execute("SELECT candidate_id FROM candidates WHERE email = ?", (email["to"].lower(),)).fetchone()
        cid = r["candidate_id"] if r else None
    return sync.applicant_for(conn, cid) if cid else None


def _email_text(item_id: str, label: str, email: dict) -> str:
    return (f"HireGuard: {_esc(label)} after human approval (item {_esc(item_id)}).\n"
            f"To: {_esc(email.get('to', ''))}\nSubject: {_esc(email.get('subject', ''))}\n\n{_esc(email.get('body', ''))}")


def _log_email(applicant_id: int, item_id: str, label: str, email: dict) -> dict:
    body = _email_text(item_id, label, email)
    if SEND_EMAIL:
        partner = odoo_client.call("hr.applicant", "read", [applicant_id], fields=["partner_id"])
        partner_id = partner[0]["partner_id"][0] if partner and partner[0].get("partner_id") else None
        if partner_id is None:
            raise OdooError(f"applicant {applicant_id} has no contact to email")
        odoo_client.call("hr.applicant", "message_post", [applicant_id], body=_esc(email.get("body", "")),
                         subject=_esc(email.get("subject", "")), message_type="comment",
                         subtype_xmlid="mail.mt_comment", partner_ids=[partner_id])
        return {"applicant_id": applicant_id, "emailed": True}
    _note(applicant_id, body)
    return {"applicant_id": applicant_id, "noted": True}

# ---------------------------------------------------------------- mirrors


def _shortlist_stage_id() -> int:
    rows = odoo_client.search_read("hr.recruitment.stage", [("name", "=", odoo_client.SHORTLIST_STAGE)], ["id"], limit=1)
    if rows:
        return rows[0]["id"]
    return odoo_client.call("hr.recruitment.stage", "create", {"name": odoo_client.SHORTLIST_STAGE})


def _mirror_shortlist(payload: dict, conn: sqlite3.Connection, result: dict) -> dict | None:
    linked = [(cid, aid) for cid in payload["candidate_ids"] if (aid := sync.applicant_for(conn, cid))]
    if not linked:
        return None
    stage_id = _shortlist_stage_id()  # lazily: only when a linked candidate exists
    scores = payload.get("scores") or {}
    item_id = payload["approval_item_id"]
    odoo_client.call("hr.applicant", "write", [aid for _, aid in linked], {"stage_id": stage_id})
    for cid, aid in linked:
        score = scores.get(cid)
        score_txt = f"{float(score):.1f}/100" if isinstance(score, (int, float)) else "n/a"
        _note(aid, f"HireGuard: shortlisted after human approval (item {_esc(item_id)}). "
                   f"Rubric score: {_esc(score_txt)}, computed by code.")
    return {"stage_id": stage_id, "applicant_ids": [aid for _, aid in linked]}


def _mirror_email(payload: dict, conn: sqlite3.Connection, result: dict) -> dict | None:
    aid = _linked_applicant(conn, payload, payload)
    return _log_email(aid, payload["approval_item_id"], "email sent", payload) if aid else None


def _mirror_offer(payload: dict, conn: sqlite3.Connection, result: dict) -> dict | None:
    email = payload.get("email") or {}
    aid = _linked_applicant(conn, payload, email)
    return _log_email(aid, payload["approval_item_id"], "offer sent", email) if aid and email else None


@lru_cache(maxsize=1)
def _event_fields() -> frozenset[str]:
    return frozenset(odoo_client.call("calendar.event", "fields_get", attributes=["type"]))


def _mirror_interview(payload: dict, conn: sqlite3.Connection, result: dict) -> dict:
    item_id, cid = payload["approval_item_id"], payload["candidate_id"]
    aid = sync.applicant_for(conn, cid)
    name = f"Interview {cid} (HireGuard {item_id})"
    # a re-run after a failed write must not create a second event
    existing = odoo_client.search_read("calendar.event", [("name", "=", name)], ["id"], limit=1)
    if existing:
        event_id = existing[0]["id"]
    else:
        vals: dict[str, Any] = {"name": name, "start": sync.to_odoo_dt(payload["slot"]["start"]),
                                "stop": sync.to_odoo_dt(payload["slot"]["end"]),
                                "partner_ids": [(6, 0, [sync.recruiter_partner_id()])]}
        if aid and "applicant_id" in _event_fields():
            vals["applicant_id"] = aid
        event_id = odoo_client.call("calendar.event", "create", vals)
    out: dict[str, Any] = {"event_id": event_id}
    if aid and payload.get("email"):
        out["invite"] = _log_email(aid, item_id, "interview invitation sent", payload["email"])
    return out

# ---------------------------------------------------------------- calendar (read, degrades gracefully)


def free_slots(recruiter_id: str, n: int = 3, conn: sqlite3.Connection | None = None) -> list[dict]:
    candidates = _original_free_slots(recruiter_id, n * 5, conn=conn)
    if not candidates:
        return []
    try:
        busy = sync.busy_intervals(candidates[0]["start"], max(s["end"] for s in candidates))
    except OdooError:
        return candidates[:n]
    free = []
    for s in candidates:
        start, end = datetime.fromisoformat(s["start"]), datetime.fromisoformat(s["end"])
        if not any(b_start < end and b_end > start for b_start, b_end in busy):
            free.append(s)
            if len(free) == n:
                break
    return free


def install():
    """Idempotent. Does nothing when the connector is disabled."""
    global _installed, _original_free_slots
    if _installed or not odoo_client.ENABLED:
        return
    _wrap(ApprovalKind.shortlist_commit, _mirror_shortlist)
    _wrap(ApprovalKind.email_send, _mirror_email)
    _wrap(ApprovalKind.interview_booking, _mirror_interview)
    _wrap(ApprovalKind.offer, _mirror_offer)
    _original_free_slots = mock_calendar.free_slots
    mock_calendar.free_slots = free_slots
    _installed = True
