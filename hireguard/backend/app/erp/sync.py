"""Reads from Odoo: applicants + PDF CVs (imported through the untrusted CV pipeline) and recruiter busy times.

Nothing here writes to Odoo.
"""
from __future__ import annotations

import base64
import binascii
import os
import sqlite3
from datetime import datetime, timezone
from functools import lru_cache

from ..config import MAX_UPLOAD_BYTES
from ..db import connect, register_schema, tx
from ..pipeline import service
from ..scoring.jobs import JOBS
from ..workflow import audit
from ..workflow.common import now_iso
from . import odoo_client
from .odoo_client import OdooError

ODOO_DT = "%Y-%m-%d %H:%M:%S"  # Odoo stores naive UTC datetimes
RECRUITER_LOGIN = os.getenv("HG_ODOO_RECRUITER_LOGIN", "")  # empty = the bot user


@register_schema
def _schema(conn: sqlite3.Connection):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS erp_links (
            candidate_id TEXT PRIMARY KEY,
            odoo_applicant_id INTEGER NOT NULL UNIQUE,
            odoo_job_id INTEGER NOT NULL,
            attachment_checksum TEXT NOT NULL,
            imported_at TEXT NOT NULL
        );
        """
    )


def candidate_id_for(applicant_id: int) -> str:
    return f"CAND-ODOO-{int(applicant_id)}"


def applicant_for(conn: sqlite3.Connection, candidate_id: str) -> int | None:
    r = conn.execute("SELECT odoo_applicant_id FROM erp_links WHERE candidate_id = ?", (candidate_id,)).fetchone()
    return r["odoo_applicant_id"] if r else None


def odoo_job_id(job_id: str) -> int:
    title = JOBS[job_id]["title"]
    rows = odoo_client.search_read("hr.job", [("name", "=", title)], ["id"], limit=1)
    if not rows:
        raise OdooError(f"Odoo has no hr.job named {title!r} (run odoo/seed_odoo.py)")
    return rows[0]["id"]


def _m2o_name(value) -> str | None:
    return value[1] if isinstance(value, (list, tuple)) and len(value) == 2 else None


def _applicants(oj: int) -> list[dict]:
    return odoo_client.search_read("hr.applicant", [("job_id", "=", oj)],
                                   ["id", "partner_name", "email_from", "stage_id"], order="id")


def _links(applicant_ids: list[int]) -> dict[int, sqlite3.Row]:
    if not applicant_ids:
        return {}
    conn = connect()
    try:
        rows = conn.execute(f"SELECT * FROM erp_links WHERE odoo_applicant_id IN ({','.join('?' * len(applicant_ids))})",
                            applicant_ids).fetchall()
    finally:
        conn.close()
    return {r["odoo_applicant_id"]: r for r in rows}


def list_applicants(job_id: str) -> list[dict]:
    apps = _applicants(odoo_job_id(job_id))
    links = _links([a["id"] for a in apps])
    return [{"applicant_id": a["id"], "candidate_id": candidate_id_for(a["id"]), "name": a.get("partner_name") or "",
             "email": a.get("email_from") or "", "stage": _m2o_name(a.get("stage_id")), "imported": a["id"] in links}
            for a in apps]


def _cv_attachments(applicant_ids: list[int]) -> dict[int, dict]:
    """Newest PDF per applicant, metadata only (one call for all applicants; content is fetched separately)."""
    if not applicant_ids:
        return {}
    rows = odoo_client.search_read(
        "ir.attachment",
        [("res_model", "=", "hr.applicant"), ("res_id", "in", applicant_ids), ("mimetype", "=", "application/pdf")],
        ["id", "res_id", "name", "file_size", "checksum"], order="id desc")
    newest: dict[int, dict] = {}
    for r in rows:
        newest.setdefault(r["res_id"], r)
    return newest


def _attachment_b64(value) -> str | None:
    """Odoo <= 18 returns `datas` as base64 text. Odoo 19+ dropped `datas`; `raw` reads as
    {"filename", "content": base64 text, "size"}."""
    if isinstance(value, dict):
        value = value.get("content")
    return value or None


def _download(attachment_id: int) -> bytes:
    try:
        rows = odoo_client.call("ir.attachment", "read", [attachment_id], fields=["datas"])
        data = rows[0].get("datas") if rows else None
    except OdooError as e:
        if "Invalid field" not in str(e):
            raise
        rows = odoo_client.call("ir.attachment", "read", [attachment_id], fields=["raw"])
        data = rows[0].get("raw") if rows else None
    data = _attachment_b64(data)
    if not data:
        raise OdooError(f"attachment {attachment_id} has no content")
    try:
        return base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as e:
        raise OdooError(f"attachment {attachment_id}: invalid base64") from e


def import_applicants(job_id: str, actor: str) -> dict:
    oj = odoo_job_id(job_id)
    apps = _applicants(oj)
    links = _links([a["id"] for a in apps])
    atts = _cv_attachments([a["id"] for a in apps])
    imported, skipped = [], []

    for a in apps:
        aid, cid = a["id"], candidate_id_for(a["id"])
        att = atts.get(aid)
        if att is None:
            skipped.append({"applicant_id": aid, "reason": "no PDF attached"})
            continue
        if (att.get("file_size") or 0) > MAX_UPLOAD_BYTES:  # checked before downloading anything
            skipped.append({"applicant_id": aid, "reason": "PDF too large"})
            continue
        link = links.get(aid)
        if link and link["attachment_checksum"] == att.get("checksum") and service.get_candidate(cid):
            skipped.append({"applicant_id": aid, "candidate_id": cid, "reason": "already imported"})
            continue
        try:
            service.process_cv(_download(att["id"]), a.get("partner_name") or "", a.get("email_from") or "", job_id,
                               candidate_id=cid, actor=f"{actor}:odoo-import")
        except service.UploadRejected as e:
            skipped.append({"applicant_id": aid, "reason": f"rejected: {e}"})
            continue
        with tx() as conn:
            conn.execute(
                "INSERT INTO erp_links VALUES (?,?,?,?,?) ON CONFLICT(candidate_id) DO UPDATE SET "
                "odoo_job_id = excluded.odoo_job_id, attachment_checksum = excluded.attachment_checksum, "
                "imported_at = excluded.imported_at",
                (cid, aid, oj, att.get("checksum") or "", now_iso()))
        imported.append({"applicant_id": aid, "candidate_id": cid})

    audit.append(actor, "erp.import_applicants", "job", job_id,
                 {"odoo_job_id": oj, "imported": [x["candidate_id"] for x in imported],
                  "skipped": [{"applicant_id": x["applicant_id"], "reason": x["reason"]} for x in skipped]})
    return {"job_id": job_id, "imported": imported, "skipped": skipped}

# ---------------------------------------------------------------- calendar


@lru_cache(maxsize=1)
def recruiter_partner_id() -> int:
    login = RECRUITER_LOGIN or odoo_client.USER
    rows = odoo_client.search_read("res.users", [("login", "=", login)], ["partner_id"], limit=1)
    if not rows or not rows[0].get("partner_id"):
        raise OdooError(f"Odoo user {login!r} not found")
    return rows[0]["partner_id"][0]


def to_odoo_dt(iso: str) -> str:
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        raise ValueError(f"naive datetime: {iso}")
    return dt.astimezone(timezone.utc).strftime(ODOO_DT)


def _from_odoo_dt(s: str) -> datetime:
    return datetime.strptime(s, ODOO_DT).replace(tzinfo=timezone.utc)


def busy_intervals(start_iso: str, end_iso: str) -> list[tuple[datetime, datetime]]:
    rows = odoo_client.search_read(
        "calendar.event",
        [("partner_ids", "in", [recruiter_partner_id()]), ("start", "<", to_odoo_dt(end_iso)),
         ("stop", ">", to_odoo_dt(start_iso))],
        ["start", "stop"])
    return [(_from_odoo_dt(r["start"]), _from_odoo_dt(r["stop"])) for r in rows if r.get("start") and r.get("stop")]
