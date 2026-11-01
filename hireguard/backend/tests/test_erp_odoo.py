"""Odoo connector against an in-process fake Odoo (XML-RPC server in a thread, in-memory records)."""
import base64
import hashlib
import socket
import threading
from pathlib import Path
from xmlrpc.server import SimpleXMLRPCRequestHandler, SimpleXMLRPCServer

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import db as app_db
from app import main  # noqa: F401  registers every schema
from app.auth import core as auth
from app.config import DATA_DIR
from app.contracts import ApprovalKind, Role, UserOut
from app.erp import handlers, odoo_client, routes as erp_routes, sync
from app.pipeline import service
from app.scoring.jobs import JOBS
from app.workflow import approvals, executor, mock_calendar
from test_workflow import client_for, make_user

PDFS = DATA_DIR / "test_pdfs"
JOB = "JOB-DATA-01"
BOT = "hireguard-bot@example.tn"
KEY = "test-api-key"
WRITES = {"create", "write", "unlink", "message_post"}
M2O = {"stage_id": "hr.recruitment.stage", "job_id": "hr.job", "partner_id": "res.partner"}


class _Handler(SimpleXMLRPCRequestHandler):
    rpc_paths = ("/xmlrpc/2/common", "/xmlrpc/2/object")


class FakeOdoo:
    def __init__(self):
        self.records: dict[str, dict[int, dict]] = {}
        self.messages: list[dict] = []
        self.calls: list[tuple[str, str]] = []
        self._next = 100
        self.server = SimpleXMLRPCServer(("127.0.0.1", 0), requestHandler=_Handler, allow_none=True, logRequests=False)
        self.server.register_function(self.authenticate, "authenticate")
        self.server.register_function(lambda: {"server_version": "17.0-fake"}, "version")
        self.server.register_function(self.execute_kw, "execute_kw")
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    # ------------------------------------------------------------ data

    def add(self, model: str, vals: dict, rid: int | None = None) -> int:
        if rid is None:
            rid, self._next = self._next, self._next + 1
        self.records.setdefault(model, {})[rid] = {}
        self._write(model, rid, vals)
        return rid

    def _write(self, model: str, rid: int, vals: dict):
        rec = self.records[model][rid]
        for k, v in vals.items():
            if k in M2O and isinstance(v, int):
                v = [v, self.records.get(M2O[k], {}).get(v, {}).get("name", "")]
            elif isinstance(v, list) and v and isinstance(v[0], list) and v[0][0] == 6:  # (6, 0, ids) command
                v = list(v[0][2])
            rec[k] = v

    def add_applicant(self, name: str, email: str, pdf: Path, job_odoo_id: int) -> int:
        aid = self.add("hr.applicant", {"partner_name": name, "email_from": email, "job_id": job_odoo_id,
                                        "stage_id": 1, "partner_id": 3})
        data = pdf.read_bytes()
        self.add("ir.attachment", {"name": pdf.name, "res_model": "hr.applicant", "res_id": aid,
                                   "mimetype": "application/pdf", "file_size": len(data),
                                   "checksum": hashlib.sha1(data).hexdigest(),
                                   "datas": base64.b64encode(data).decode()})
        return aid

    def notes_for(self, applicant_id: int) -> list[str]:
        return [m["body"] for m in self.messages if m["res_id"] == applicant_id]

    # ------------------------------------------------------------ RPC

    def authenticate(self, db, login, key, _env):
        return 2 if (login, key) == (BOT, KEY) else False

    def execute_kw(self, db, uid, key, model, method, args, kwargs):
        if (uid, key) != (2, KEY):
            raise PermissionError("Access denied")
        self.calls.append((model, method))
        recs = self.records.setdefault(model, {})
        if method == "search_read":
            ids = self._search(model, args[0], kwargs.get("limit", 0), kwargs.get("order"))
            return [self._read(model, i, kwargs.get("fields")) for i in ids]
        if method == "search":
            return self._search(model, args[0], kwargs.get("limit", 0), None)
        if method == "read":
            return [self._read(model, i, kwargs.get("fields")) for i in args[0] if i in recs]
        if method == "create":
            return self.add(model, args[0])
        if method == "write":
            for i in args[0]:
                self._write(model, i, args[1])
            return True
        if method == "fields_get":
            fields = {f for r in recs.values() for f in r} | {"name", "start", "stop", "partner_ids", "applicant_id"}
            return {f: {"type": "char"} for f in fields}
        if method == "message_post":
            self.messages.append({"model": model, "res_id": args[0][0], **kwargs})
            return len(self.messages)
        raise ValueError(f"fake Odoo: unsupported {model}.{method}")

    def _search(self, model, domain, limit, order):
        ids = sorted(self.records.get(model, {}), reverse=bool(order and "desc" in order))
        ids = [i for i in ids if all(self._match(self.records[model][i], d) for d in domain)]
        return ids[:limit] if limit else ids

    @staticmethod
    def _match(rec, cond):
        field, op, value = cond
        v = rec.get(field)
        if isinstance(v, list) and len(v) == 2 and isinstance(v[1], str):
            v = v[0]  # many2one [id, name]
        if op == "=":
            return v == value
        if op == "in":
            return bool(set(v) & set(value)) if isinstance(v, list) else v in value
        if op == "<":
            return v is not None and v < value
        if op == ">":
            return v is not None and v > value
        raise ValueError(f"fake Odoo: unsupported operator {op}")

    def _read(self, model, rid, fields):
        rec = self.records[model][rid]
        return {"id": rid, **{f: rec.get(f, False) for f in (fields or rec) if f != "id"}}


def _clear_caches():
    odoo_client._uid.cache_clear()
    sync.recruiter_partner_id.cache_clear()
    handlers._event_fields.cache_clear()


def _dead_url() -> str:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}"


@pytest.fixture
def odoo(tmp_path, monkeypatch):
    monkeypatch.setattr(app_db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setenv("HG_ANCHOR_LOOP", "0")
    app_db.init_db()
    monkeypatch.setattr(service, "extract_cv", lambda text: None)  # offline: no model call in tests

    fake = FakeOdoo()
    fake.add("res.partner", {"name": "HireGuard bot"}, rid=3)
    fake.add("res.users", {"login": BOT, "partner_id": 3}, rid=2)
    fake.add("hr.recruitment.stage", {"name": "New"}, rid=1)
    fake.job_id = fake.add("hr.job", {"name": JOBS[JOB]["title"]})

    monkeypatch.setattr(odoo_client, "ENABLED", True)
    monkeypatch.setattr(odoo_client, "URL", fake.url)
    monkeypatch.setattr(odoo_client, "API_KEY", KEY)
    monkeypatch.setattr(odoo_client, "USER", BOT)
    monkeypatch.setattr(handlers, "_installed", False)
    _clear_caches()
    saved_handlers, saved_free_slots = dict(executor._handlers), mock_calendar.free_slots
    handlers.install()
    try:
        yield fake
    finally:
        executor._handlers.clear()
        executor._handlers.update(saved_handlers)
        mock_calendar.free_slots = saved_free_slots
        _clear_caches()
        fake.stop()


def erp_client(user: UserOut) -> TestClient:
    app = FastAPI()
    app.include_router(erp_routes.router, prefix="/api")
    c = TestClient(app)
    token, csrf = auth.create_session(user.id)
    c.cookies.set(auth.SESSION_COOKIE, token)
    c.headers["X-CSRF-Token"] = csrf
    return c


def _import_one(fake, pdf="clean.pdf", name="Amel Jaziri", email="amel.jaziri@example.tn") -> tuple[int, str]:
    aid = fake.add_applicant(name, email, PDFS / pdf, fake.job_id)
    sync.import_applicants(JOB, actor="rec1")
    return aid, sync.candidate_id_for(aid)


def _writes(fake) -> list:
    return [c for c in fake.calls if c[1] in WRITES]

# ---------------------------------------------------------------- tests


def test_import_goes_through_untrusted_pipeline(odoo):
    rec = make_user(Role.recruiter, "rec1")
    clean = odoo.add_applicant("Amel Jaziri", "amel.jaziri@example.tn", PDFS / "clean.pdf", odoo.job_id)
    poisoned = odoo.add_applicant("Karim Mansouri", "karim.mansouri@example.tn", PDFS / "white_text.pdf", odoo.job_id)

    r = erp_client(rec).post(f"/api/erp/jobs/{JOB}/import")
    assert r.status_code == 200, r.text
    assert {x["applicant_id"] for x in r.json()["imported"]} == {clean, poisoned}

    flagged = {f["candidate_id"] for f in service.security_findings()}
    assert sync.candidate_id_for(poisoned) in flagged
    assert sync.candidate_id_for(clean) not in flagged
    assert service.get_candidate(sync.candidate_id_for(poisoned))["hidden_findings"]
    assert not _writes(odoo), "importing must never write to Odoo"

    again = erp_client(rec).post(f"/api/erp/jobs/{JOB}/import").json()
    assert again["imported"] == []
    assert {x["reason"] for x in again["skipped"]} == {"already imported"}

    listed = erp_client(rec).get(f"/api/erp/jobs/{JOB}/applicants").json()
    assert all(a["imported"] for a in listed) and len(listed) == 2


def test_write_only_after_approval(odoo):
    rec, hrm = make_user(Role.recruiter, "rec1"), make_user(Role.hr_manager, "hrm1")
    aid, cid = _import_one(odoo)
    item = approvals.create_item(ApprovalKind.shortlist_commit, "Commit shortlist",
                                 {"job_id": JOB, "candidate_ids": [cid], "scores": {cid: 61.5}}, created_by="rec1")

    assert client_for(rec).post(f"/api/executor/run/{item.id}").status_code == 403
    assert not _writes(odoo)

    assert client_for(hrm).post(f"/api/approvals/{item.id}/decision", json={"decision": "approve"}).status_code == 200
    r = client_for(rec).post(f"/api/executor/run/{item.id}")
    assert r.status_code == 200, r.text
    assert odoo.records["hr.applicant"][aid]["stage_id"][1] == odoo_client.SHORTLIST_STAGE
    notes = odoo.notes_for(aid)
    assert len(notes) == 1 and "human approval" in notes[0] and "61.5/100" in notes[0]


def test_rollback_when_odoo_fails(odoo, monkeypatch):
    rec, hrm = make_user(Role.recruiter, "rec1"), make_user(Role.hr_manager, "hrm1")
    aid, cid = _import_one(odoo)
    item = approvals.create_item(ApprovalKind.email_send, "Reply",
                                 {"to": "amel.jaziri@example.tn", "subject": "Next steps",
                                  "body": "<script>alert(1)</script>", "candidate_id": cid,
                                  "recipient_verified": True}, created_by="system")
    assert client_for(hrm).post(f"/api/approvals/{item.id}/decision", json={"decision": "approve"}).status_code == 200

    monkeypatch.setattr(odoo_client, "URL", _dead_url())
    r = client_for(rec).post(f"/api/executor/run/{item.id}")
    assert r.status_code == 502 and "nothing was executed" in r.json()["detail"]
    conn = app_db.connect()
    assert conn.execute("SELECT COUNT(*) FROM email_outbox WHERE approval_item_id = ?", (item.id,)).fetchone()[0] == 0
    conn.close()
    assert approvals.get_item(item.id).status == "approved"

    monkeypatch.setattr(odoo_client, "URL", odoo.url)
    assert client_for(rec).post(f"/api/executor/run/{item.id}").status_code == 200
    [note] = odoo.notes_for(aid)
    assert "&lt;script&gt;" in note and "<script>" not in note


def test_busy_odoo_slots_are_skipped(odoo):
    first = handlers._original_free_slots("recruiter", 3)[0]
    odoo.add("calendar.event", {"name": "Busy", "partner_ids": [3],
                                "start": sync.to_odoo_dt(first["start"]), "stop": sync.to_odoo_dt(first["end"])})
    slots = mock_calendar.free_slots("recruiter", 3)
    assert len(slots) == 3 and first["id"] not in {s["id"] for s in slots}


def test_calendar_degrades_when_odoo_is_down(odoo, monkeypatch):
    monkeypatch.setattr(odoo_client, "URL", _dead_url())
    assert mock_calendar.free_slots("recruiter", 3) == handlers._original_free_slots("recruiter", 3)


def test_status_and_disabled_connector(odoo, monkeypatch):
    rec = make_user(Role.recruiter, "rec1")
    st = erp_client(rec).get("/api/erp/status").json()
    assert st["enabled"] and st["connected"] and st["uid"] == 2
    assert KEY not in str(st)

    monkeypatch.setattr(odoo_client, "ENABLED", False)
    assert erp_client(rec).post(f"/api/erp/jobs/{JOB}/import").status_code == 409
    assert erp_client(rec).post("/api/erp/jobs/JOB-NOPE-99/import").status_code == 404
    emp = make_user(Role.employee, "emp1")
    assert erp_client(emp).get("/api/erp/status").status_code == 403


def test_download_falls_back_to_raw_on_odoo_19_plus(monkeypatch):
    """Odoo 19+ removed ir.attachment.datas; `raw` reads as {"filename", "content": base64, "size"}."""
    pdf = (PDFS / "clean.pdf").read_bytes()
    asked = []

    def fake_call(model, method, ids, fields):
        asked.append(fields)
        if fields == ["datas"]:
            raise odoo_client.OdooError("ValueError: Invalid field 'datas' on 'ir.attachment'")
        return [{"id": ids[0], "raw": {"filename": "cv.pdf", "content": base64.b64encode(pdf).decode(), "size": len(pdf)}}]

    monkeypatch.setattr(sync.odoo_client, "call", fake_call)
    assert sync._download(7) == pdf
    assert asked == [["datas"], ["raw"]]


def test_download_does_not_hide_other_odoo_errors(monkeypatch):
    def fake_call(model, method, ids, fields):
        raise odoo_client.OdooError("AccessError: not allowed")

    monkeypatch.setattr(sync.odoo_client, "call", fake_call)
    with pytest.raises(odoo_client.OdooError, match="AccessError"):
        sync._download(7)