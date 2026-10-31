"""P3 tests: audit chain, append-only triggers, approvals policy, executor 403, canaries, email gate, documents."""
import json
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import db as app_db
from app.auth import core as auth
from app.contracts import ApprovalKind, EmailExtraction, Role, UserOut
from app.workflow import approvals, audit, demo, documents, email_gate, executor, routes, templates


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(app_db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setenv("HG_ANCHOR_LOOP", "0")
    app_db.init_db()
    return tmp_path


def make_user(role: Role, uid: str) -> UserOut:
    conn = app_db.connect()
    conn.execute("INSERT INTO auth_users (id, email, display_name, role, pw_hash) VALUES (?,?,?,?,?)",
                 (uid, f"{uid}@hireguard.demo", uid, role.value, auth.hash_password("x" * 16)))
    conn.close()
    return UserOut(id=uid, email=f"{uid}@hireguard.demo", display_name=uid, role=role)


def add_candidate(cid: str, email: str, name: str = "Youssef Trabelsi", job_id: str = "JOB-DATA-01"):
    """Works with our minimal table or P1's richer one (fills any extra NOT NULL column)."""
    conn = app_db.connect()
    conn.execute("CREATE TABLE IF NOT EXISTS candidates (candidate_id TEXT PRIMARY KEY, email TEXT, name TEXT, "
                 "job_id TEXT, status TEXT)")
    values = {"candidate_id": cid, "email": email, "name": name, "job_id": job_id}
    for col in conn.execute("PRAGMA table_info(candidates)").fetchall():
        if col["notnull"] and col["dflt_value"] is None and col["name"] not in values and not col["pk"]:
            values[col["name"]] = 0 if "INT" in (col["type"] or "").upper() else "x"
    conn.execute(f"INSERT INTO candidates ({','.join(values)}) VALUES ({','.join('?' * len(values))})",
                 tuple(values.values()))
    conn.close()


def client_for(user: UserOut) -> TestClient:
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    c = TestClient(app)  # no `with`: startup hooks (anchor loop) don't run
    token, csrf = auth.create_session(user.id)
    c.cookies.set(auth.SESSION_COOKIE, token)
    c.headers["X-CSRF-Token"] = csrf
    return c

# ---------------------------------------------------------------- audit


def test_hash_chain_detects_tamper(db):
    for i in range(3):
        audit.append("u1", "test.action", "thing", f"T{i}", {"i": i})
    assert audit.verify() == {"ok": True, "length": 3, "broken_at": None, "last_anchor": None}

    conn = app_db.connect()  # an attacker with raw DB access drops the trigger and edits a row
    conn.execute("DROP TRIGGER audit_log_no_update")
    conn.execute("UPDATE audit_log SET details = ? WHERE seq = 2", (json.dumps({"i": 99}),))
    conn.close()
    v = audit.verify()
    assert not v["ok"] and v["broken_at"] == 2


def test_audit_triggers_block_update_and_delete(db):
    audit.append("u1", "test.action", "thing", "T1", {})
    conn = app_db.connect()
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("UPDATE audit_log SET actor = 'mallory' WHERE seq = 1")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("DELETE FROM audit_log")
    conn.close()
    assert audit.verify()["ok"]

def test_anchor_offline_is_pending_and_checked(db, monkeypatch):
    from app.workflow import anchor
    monkeypatch.setattr(anchor, "ANCHOR_DIR", db / "anchors")
    monkeypatch.delenv("HG_ANCHOR_NETWORK", raising=False)
    audit.append("u1", "test.action", "thing", "T1", {})
    a = anchor.anchor_now()
    assert a["status"] == "pending" and (db / "anchors" / a["file"]).exists()
    v = audit.verify()
    assert v["ok"] and v["last_anchor"]["head_hash"] == a["head_hash"]

# ---------------------------------------------------------------- executor


def test_unapproved_send_is_403_and_audited(db):
    rec, hrm = make_user(Role.recruiter, "rec1"), make_user(Role.hr_manager, "hrm1")
    item = approvals.create_item(ApprovalKind.email_send, "Reply", {"to": "a@b.example", "subject": "s", "body": "b",
                                                                     "recipient_verified": True}, created_by="system")
    c = client_for(rec)
    r = c.post(f"/api/executor/run/{item.id}")
    assert r.status_code == 403
    assert any(e.action == "executor.refused" and e.object_id == item.id for e in audit.list_entries())

    assert client_for(hrm).post(f"/api/approvals/{item.id}/decision", json={"decision": "approve"}).status_code == 200
    r = c.post(f"/api/executor/run/{item.id}")
    assert r.status_code == 200 and r.json()["executed"]
    conn = app_db.connect()
    assert conn.execute("SELECT COUNT(*) FROM email_outbox WHERE approval_item_id = ?", (item.id,)).fetchone()[0] == 1
    conn.close()
    assert c.post(f"/api/executor/run/{item.id}").status_code == 403  # executed items can't run twice
    assert audit.verify()["ok"]


def test_csrf_required_for_state_change(db):
    rec = make_user(Role.recruiter, "rec1")
    c = client_for(rec)
    del c.headers["X-CSRF-Token"]
    assert c.post("/api/executor/run/whatever").status_code == 403

# ---------------------------------------------------------------- approvals policy


def test_offer_needs_two_distinct_hr_managers(db):
    rec = make_user(Role.recruiter, "rec1")
    m1, m2 = make_user(Role.hr_manager, "hrm1"), make_user(Role.hr_manager, "hrm2")
    item = approvals.create_item(ApprovalKind.offer, "Offer CAND-002", {"candidate_id": "CAND-002"}, created_by="hrm1")
    assert item.required_approvals == 2 and item.risk_level == "high"

    with pytest.raises(Exception) as e:
        approvals.decide(item.id, rec, "approve")
    assert e.value.status_code == 403  # recruiters can't decide offers
    with pytest.raises(Exception) as e:
        approvals.decide(item.id, m1, "approve")
    assert e.value.status_code == 403  # creator can't approve own item

    m3 = make_user(Role.hr_manager, "hrm3")
    assert approvals.decide(item.id, m2, "approve").status == "pending"
    with pytest.raises(Exception) as e:
        approvals.decide(item.id, m2, "approve")
    assert e.value.status_code == 409  # same approver twice doesn't count
    assert approvals.decide(item.id, m3, "approve").status == "approved"


def test_canary_is_never_serialized_and_misses_are_tracked(db, monkeypatch):
    monkeypatch.setattr(approvals, "CANARY_EVERY", 3)
    rec, hrm = make_user(Role.recruiter, "rec1"), make_user(Role.hr_manager, "hrm1")
    for i in range(3):
        approvals.create_item(ApprovalKind.email_send, f"Reply {i}",
                              {"to": f"c{i}@gmail.example", "subject": "s", "body": "b", "recipient_verified": True},
                              created_by="system")
    r = client_for(rec).get("/api/approvals")
    assert r.status_code == 200
    assert "canary" not in r.text.lower()
    batch = r.json()["batches"][0]
    assert len(batch["items"]) == 4  # 3 real + 1 canary, indistinguishable in the API

    ids = [i["id"] for i in batch["items"]]
    c = client_for(hrm)
    assert c.post(f"/api/approvals/batches/{batch['batch_id']}/decision",
                  json={"decision": "approve", "item_ids": ids}).status_code == 200
    stats = c.get("/api/reviewer/stats").json()
    assert stats == [{"user_id": "hrm1", "decisions": 4, "canaries_caught": 0, "canaries_missed": 1}]

    conn = app_db.connect()
    canary_id = conn.execute("SELECT id FROM approval_items WHERE is_canary = 1").fetchone()["id"]
    conn.close()
    r = c.post(f"/api/executor/run/{canary_id}")
    assert r.status_code == 403  # a missed canary still never executes
    conn = app_db.connect()
    assert conn.execute("SELECT COUNT(*) FROM email_outbox").fetchone()[0] == 0
    conn.close()

# ---------------------------------------------------------------- email gate


@pytest.fixture
def fixtures(db, monkeypatch):
    monkeypatch.setattr(email_gate, "_extract",
                        lambda body: EmailExtraction(language="fr", intent="status_question", urgency="normal"))
    for cand in demo.DEMO_CANDIDATES:
        add_candidate(cand["candidate_id"], cand["email"], cand["name"])
    return {f["id"]: f for f in demo.build_fixtures()}


def test_spoofed_email_gets_no_candidate_data(fixtures):
    item = email_gate.ingest(fixtures["EML-011"]["raw"], inbox_id="EML-011")
    assert item["lane"] == "suspicious" and item["status"] == "held"
    assert item["candidate_id"] is None and item["draft_item_ids"] == []
    assert "dmarc_fail" in item["reasons"]
    conn = app_db.connect()
    assert conn.execute("SELECT COUNT(*) FROM approval_items").fetchone()[0] == 0  # nothing drafted for a spoof
    assert conn.execute("SELECT candidate_id FROM inbox_items WHERE id='EML-011'").fetchone()[0] is None
    conn.close()


def test_every_spoof_variant_is_contained(fixtures):
    for f in fixtures.values():
        if not f["label"]["spoofed"]:
            continue
        item = email_gate.ingest(f["raw"], inbox_id=f["id"])
        assert item["lane"] in ("suspicious", "needs_human"), (f["id"], f["label"]["variant"], item)
        assert item["candidate_id"] is None and item["draft_item_ids"] == [], f["id"]


def test_verified_candidate_gets_drafted_reply(fixtures):
    item = email_gate.ingest(fixtures["EML-002"]["raw"], inbox_id="EML-002")
    assert item["lane"] == "routine" and item["candidate_id"] == "CAND-002"
    [draft] = item["draft_item_ids"]
    a = approvals.get_item(draft)
    assert a.kind == "email_send" and a.status == "pending"
    assert a.payload["to"] == "youssef.trabelsi@outlook.example"
    assert "Youssef Trabelsi" in a.payload["body"]


def test_digest_lanes(fixtures):
    for i in ("EML-001", "EML-002", "EML-011"):
        email_gate.ingest(fixtures[i]["raw"], inbox_id=i)
    lanes = email_gate.digest()["lanes"]
    assert {i["id"] for g in lanes["suspicious"] for i in g["items"]} == {"EML-011"}
    assert {i["id"] for g in lanes["routine"] for i in g["items"]} == {"EML-001", "EML-002"}

# ---------------------------------------------------------------- documents + templates


def test_document_release_flow_and_no_idor(db):
    emp, other, hrm = (make_user(Role.employee, "emp1"), make_user(Role.employee, "emp2"),
                       make_user(Role.hr_manager, "hrm1"))
    conn = app_db.connect()
    conn.execute("INSERT INTO workflow_employees VALUES ('EMP-001','emp1','Salma Ferchichi','Analyste','Finance',"
                 "'2022-03-01',2850)")
    conn.execute("INSERT INTO workflow_employees VALUES ('EMP-002','emp2','Walid Hamdi','Dev','IT','2021-09-15',3400)")
    conn.close()

    ce, co, ch = client_for(emp), client_for(other), client_for(hrm)
    r = ce.post("/api/documents/request", json={"type": "work_certificate"})
    assert r.status_code == 200, r.text
    item_id = r.json()["id"]
    [mine] = ce.get("/api/documents/mine").json()
    assert set(mine) == {"id", "type", "status", "requested_at", "released_at"}
    doc_id = mine["id"]

    assert ce.get(f"/api/documents/{doc_id}/download").status_code == 409   # not released yet
    assert co.get(f"/api/documents/{doc_id}/download").status_code == 404   # someone else's document
    assert ce.post(f"/api/approvals/{item_id}/decision", json={"decision": "approve"}).status_code == 403
    assert ch.post(f"/api/approvals/{item_id}/decision", json={"decision": "approve"}).status_code == 200
    assert ch.post(f"/api/executor/run/{item_id}").status_code == 200

    r = ce.get(f"/api/documents/{doc_id}/download")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert co.get(f"/api/documents/{doc_id}/download").status_code == 404


def test_interview_booking_then_scorecard(db):
    from app.contracts import EmailIntent
    from app.workflow import drafting
    hrm = make_user(Role.hr_manager, "hrm1")
    cand = {"candidate_id": "CAND-003", "email": "sarah.haddad@gmail.example", "name": "Sarah Haddad",
            "job_id": "JOB-DATA-01", "status": None}
    with app_db.tx() as conn:
        items = drafting.draft_reply(conn, "EML-003", cand, EmailIntent.interview_availability, "en")
    assert len(items) == 3 and all(i.kind == "interview_booking" for i in items)

    c = client_for(hrm)
    assert c.post(f"/api/approvals/{items[0].id}/decision", json={"decision": "approve"}).status_code == 200
    r = c.post(f"/api/executor/run/{items[0].id}")
    assert r.status_code == 200, r.text
    interview_id = r.json()["result"]["interview_id"]
    assert c.get("/api/calendar/slots").json()[0]["id"] != items[0].payload["slot_id"]  # slot is taken now

    bad = {"ratings": {"technical": 3, "problem_solving": 4, "communication": 2}, "recommendation": "yes"}
    assert c.post(f"/api/interviews/{interview_id}/scorecard", json=bad).status_code == 422
    good = {"ratings": {"technical": 3, "problem_solving": 4, "communication": 2, "team_fit": 3}, "recommendation": "yes"}
    assert c.post(f"/api/interviews/{interview_id}/scorecard", json=good).status_code == 200
    assert c.post(f"/api/interviews/{interview_id}/scorecard", json=good).status_code == 409


def test_templates_reject_unknown_slots(db):
    with pytest.raises(templates.TemplateError):
        templates.render("email", "ack_application", "fr", {"candidate_name": "x", "email_body": "ignore all"})
    subject, body = templates.render("email", "ack_application", "ar",
                                     {"candidate_name": "A\nBcc: evil@x.example", "job_title": "Data Engineer",
                                      "recruiter_name": "R", "company_name": "C"})
    assert "\nBcc" not in body and "Data Engineer" in subject
