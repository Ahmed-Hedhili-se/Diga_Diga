import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import db
from app.auth.core import SESSION_COOKIE, create_session, hash_password
from app.scoring import money, routes

try:  # register P3's tables (audit/approvals) before init_db when they exist
    import app.workflow.approvals  # noqa: F401
    import app.workflow.audit  # noqa: F401
    import app.workflow.executor  # noqa: F401
    import app.pipeline.service  # noqa: F401  (candidates table)
except ImportError:
    pass


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    conn = db.connect()
    for uid, role in (("u-rec", "recruiter"), ("u-hrm", "hr_manager"), ("u-emp", "employee")):
        conn.execute("INSERT INTO auth_users (id, email, display_name, role, pw_hash) VALUES (?,?,?,?,?)",
                     (uid, f"{uid}@t", uid, role, hash_password("x" * 12)))
    conn.close()
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    return TestClient(app)


def login(client, uid):
    token, csrf = create_session(uid)
    client.cookies.set(SESSION_COOKIE, token)
    return {"X-CSRF-Token": csrf}


def test_jobs_and_rubric_roles(client):
    assert client.get("/api/jobs").status_code == 401
    login(client, "u-emp")
    assert client.get("/api/jobs").status_code == 403
    login(client, "u-rec")
    assert {j["job_id"] for j in client.get("/api/jobs").json()} == {"JOB-DATA-01", "JOB-FS-02", "JOB-HR-03"}
    r = client.get("/api/jobs/JOB-DATA-01/rubric").json()
    assert client.get("/api/jobs/NOPE/rubric").status_code == 404
    h = login(client, "u-rec")
    assert client.put("/api/jobs/JOB-DATA-01/rubric", json=r, headers=h).status_code == 403  # recruiter can't edit


def test_rubric_put_by_manager_and_csrf(client):
    h = login(client, "u-hrm")
    r = client.get("/api/jobs/JOB-FS-02/rubric").json()
    r["min_years"] = 3
    assert client.put("/api/jobs/JOB-FS-02/rubric", json=r).status_code == 403  # no CSRF header
    assert client.put("/api/jobs/JOB-FS-02/rubric", json=r, headers=h).status_code == 200
    assert client.get("/api/jobs/JOB-FS-02/rubric").json()["min_years"] == 3
    r["skill_weights"]["react"] = -1
    assert client.put("/api/jobs/JOB-FS-02/rubric", json=r, headers=h).status_code == 400
    r["job_id"] = "JOB-HR-03"
    assert client.put("/api/jobs/JOB-FS-02/rubric", json=r, headers=h).status_code == 400


def test_money_dashboard(client):
    money.record_activity("cv_screening", 30)
    money.record_activity("documents", 6)
    h = login(client, "u-hrm")
    assert client.put("/api/money/settings", json={"hourly_cost_tnd": 30}, headers=h).status_code == 200
    m = client.get("/api/money").json()
    assert m["hours_saved"]["cv_screening"] == 3.0 and m["hours_saved"]["documents"] == 1.0
    assert m["roi_tnd"] == 120
    assert len(m["roles"]) == 3
    assert client.put("/api/money/settings", json={"hourly_cost_tnd": -1}, headers=h).status_code == 422


def test_shortlist_requires_scores(client):
    h = login(client, "u-rec")
    resp = client.post("/api/jobs/JOB-DATA-01/shortlist", json={"candidate_ids": ["CAND-404"]}, headers=h)
    assert resp.status_code == 400


def test_eval_summary_not_run_or_present(client):
    login(client, "u-hrm")
    assert client.get("/api/eval/summary").status_code == 200


def test_eval_summary_labels_every_run(client, tmp_path, monkeypatch):
    """The tab must never show a code-path (oracle) number as a model result, nor go blank when the
    harness output is kept under a per-run name."""
    import json
    monkeypatch.setattr(routes, "EVAL_DIR", tmp_path)
    login(client, "u-hrm")
    assert client.get("/api/eval/summary").json() == {"status": "not_run", "runs": []}

    sec = {"attack_success": {"k": 0, "n": 40}}
    (tmp_path / "summary_oracle.json").write_text(json.dumps({
        "generated_at": "2026-10-31T20:00:00", "extraction_mode": "oracle",
        "sections": {"attacks": sec | {"extraction_mode": "oracle"}}}), encoding="utf-8")
    (tmp_path / "summary_unmasked_qwen3-8b.json").write_text(json.dumps({
        "generated_at": "2026-10-31T21:00:00", "model": "qwen3:8b", "sections": {"attacks": sec}}), encoding="utf-8")
    (tmp_path / "baseline.json").write_text(json.dumps({"vulnerable_screener": {"attack_success": {"k": 13, "n": 40}}}),
                                            encoding="utf-8")

    default = client.get("/api/eval/summary").json()
    assert default["run"]["id"] == "unmasked_qwen3-8b" and default["run"]["mode"] == "llm"
    assert "before identity masking" in default["run"]["label"]
    assert default["sections"]["attacks"]["extraction_mode"] == "llm"          # older file, labelled by its run
    assert default["baseline"]["vulnerable_screener"]["attack_success"]["k"] == 13
    assert {r["id"] for r in default["runs"]} == {"oracle", "unmasked_qwen3-8b"}

    oracle = client.get("/api/eval/summary?run=oracle").json()
    assert oracle["sections"]["attacks"]["extraction_mode"] == "oracle" and "baseline" not in oracle
    assert client.get("/api/eval/summary?run=nope").status_code == 404


def test_status_change_is_an_approval_item_until_executed(client):
    """P3 handoff H4: object_type=candidate, object_id, status_to; nothing changes before approval."""
    from app.workflow import executor
    from app.contracts import Role, UserOut
    conn = db.connect()
    conn.execute("INSERT INTO candidates VALUES ('CAND-001','A','a@t','JOB-DATA-01','ok','D1','2026-10-31')")
    conn.close()
    h = login(client, "u-rec")
    url = "/api/jobs/JOB-DATA-01/candidates/{}/status"
    assert client.post(url.format("CAND-404"), json={"status_to": "rejected"}, headers=h).status_code == 404
    assert client.post("/api/jobs/JOB-FS-02/candidates/CAND-001/status", json={"status_to": "rejected"},
                       headers=h).status_code == 404  # right candidate, wrong job
    assert client.post(url.format("CAND-001"), json={"status_to": "applied"}, headers=h).status_code == 422
    item = client.post(url.format("CAND-001"), json={"status_to": "rejected"}, headers=h).json()
    assert item["kind"] == "status_change" and item["status"] == "pending"
    assert {"object_type": "candidate", "object_id": "CAND-001", "status_to": "rejected",
            "status_from": "applied"}.items() <= item["payload"].items()
    conn = db.connect()
    assert routes._hiring_status(conn, "CAND-001") == "applied"  # proposed only
    conn.execute("UPDATE approval_items SET status='approved' WHERE id=?", (item["id"],))
    conn.close()
    executor.run(item["id"], UserOut(id="u-hrm", email="u-hrm@t", display_name="u", role=Role.hr_manager))
    conn = db.connect()
    assert routes._hiring_status(conn, "CAND-001") == "rejected"
    conn.close()
    assert client.post(url.format("CAND-001"), json={"status_to": "rejected"}, headers=h).status_code == 409
