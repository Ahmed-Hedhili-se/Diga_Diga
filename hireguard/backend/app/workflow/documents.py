"""Self-service HR documents: generated from templates, released only after one HR click (approval + executor)."""
import json
import sqlite3
from datetime import date
from typing import Literal

import fitz  # PyMuPDF
from fastapi import HTTPException
from pydantic import BaseModel, model_validator

from ..contracts import ApprovalKind, Role, UserOut
from ..db import connect, register_schema, tx
from . import approvals, audit, templates
from .common import canonical_json, new_id, now, now_iso

DocType = Literal["work_certificate", "salary_certificate", "leave_confirmation"]
COMPANY = "HireGuard Demo SARL"


class LeaveParams(BaseModel):
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def _check(self):
        if self.end_date < self.start_date or (self.end_date - self.start_date).days > 30:
            raise ValueError("leave must be 1 to 31 days, end after start")
        return self


class DocumentRequest(BaseModel):
    type: DocType
    params: dict = {}


@register_schema
def _schema(conn: sqlite3.Connection):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS workflow_employees (
            employee_id TEXT PRIMARY KEY,
            user_id TEXT UNIQUE,
            full_name TEXT NOT NULL,
            position TEXT NOT NULL,
            department TEXT NOT NULL,
            hire_date TEXT NOT NULL,
            monthly_salary_tnd INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            employee_id TEXT NOT NULL REFERENCES workflow_employees(employee_id),
            owner_user_id TEXT NOT NULL,
            type TEXT NOT NULL,
            params TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('requested','released','rejected')),
            approval_item_id TEXT,
            created_at TEXT NOT NULL,
            released_at TEXT,
            pdf BLOB
        );
        """
    )


def _employee_for(conn, user_id: str):
    r = conn.execute("SELECT * FROM workflow_employees WHERE user_id = ?", (user_id,)).fetchone()
    if not r:
        raise HTTPException(404, "no employee record linked to this account")
    return r


def request_document(user: UserOut, req: DocumentRequest) -> dict:
    params = LeaveParams(**req.params).model_dump(mode="json") if req.type == "leave_confirmation" else {}
    with tx() as conn:
        emp = _employee_for(conn, user.id)
        doc_id = new_id("DOC")
        conn.execute("INSERT INTO documents (id, employee_id, owner_user_id, type, params, status, created_at) "
                     "VALUES (?,?,?,?,?, 'requested', ?)",
                     (doc_id, emp["employee_id"], user.id, req.type, canonical_json(params), now_iso()))
        label = req.type.replace("_", " ")
        item = approvals.create_item(
            ApprovalKind.document_release, f"Release {label} for {emp['full_name']}",
            {"document_id": doc_id, "type": req.type, "employee_id": emp["employee_id"], "params": params},
            created_by=user.id,
            diff={"before": {"status": "requested"}, "after": {"status": "released", "type": req.type, **params}},
            conn=conn)
        conn.execute("UPDATE documents SET approval_item_id = ? WHERE id = ?", (item.id, doc_id))
        audit.append(user.id, "document.request", "document", doc_id, {"type": req.type}, conn=conn)
    return item.model_dump(mode="json")


def _render_pdf(emp, doc_type: str, params: dict, doc_id: str) -> bytes:
    slots = {"employee_name": emp["full_name"], "position": emp["position"], "department": emp["department"],
             "hire_date": emp["hire_date"], "company_name": COMPANY, "issue_date": now().date().isoformat(),
             "document_ref": doc_id}
    if doc_type == "salary_certificate":
        slots["monthly_salary_tnd"] = f"{emp['monthly_salary_tnd']:,}".replace(",", " ")
    if doc_type == "leave_confirmation":
        start, end = date.fromisoformat(params["start_date"]), date.fromisoformat(params["end_date"])
        slots |= {"leave_start": start.isoformat(), "leave_end": end.isoformat(), "leave_days": (end - start).days + 1}
    title, body = templates.render("documents", doc_type, "fr", slots)

    pdf = fitz.open()
    page = pdf.new_page(width=595, height=842)  # A4
    page.insert_text((60, 90), COMPANY, fontsize=11, fontname="helv")
    page.insert_textbox(fitz.Rect(60, 140, 535, 190), title, fontsize=18, fontname="hebo", align=1)
    page.insert_textbox(fitz.Rect(60, 220, 535, 760), body, fontsize=11, fontname="helv")
    pdf.set_metadata({"title": title, "producer": "HireGuard", "creator": "HireGuard"})
    data = pdf.tobytes()
    pdf.close()
    return data


def release(conn: sqlite3.Connection, doc_id: str) -> dict:
    """Executor handler only: runs after the approval."""
    d = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    if not d or d["status"] != "requested":
        raise HTTPException(409, "document is not awaiting release")
    emp = conn.execute("SELECT * FROM workflow_employees WHERE employee_id = ?", (d["employee_id"],)).fetchone()
    pdf = _render_pdf(emp, d["type"], json.loads(d["params"]), doc_id)
    conn.execute("UPDATE documents SET status='released', released_at=?, pdf=? WHERE id=?", (now_iso(), pdf, doc_id))
    return {"document_id": doc_id, "status": "released", "bytes": len(pdf)}


def list_mine(user: UserOut) -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute("SELECT id, type, status, created_at AS requested_at, released_at FROM documents "
                            "WHERE owner_user_id = ? ORDER BY created_at DESC", (user.id,)).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def download(doc_id: str, user: UserOut) -> tuple[bytes, str]:
    conn = connect()
    try:
        d = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    finally:
        conn.close()
    # 404 for "not yours" too, so document IDs can't be enumerated (no IDOR)
    if not d or (user.role != Role.hr_manager and d["owner_user_id"] != user.id):
        raise HTTPException(404, "document not found")
    if d["status"] != "released":
        raise HTTPException(409, "document has not been released by HR yet")
    audit.append(user.id, "document.download", "document", doc_id, {"type": d["type"]})
    return d["pdf"], f"{d['type']}-{doc_id}.pdf"
