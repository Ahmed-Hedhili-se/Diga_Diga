import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import db
from app.auth.core import SESSION_COOKIE, create_session, hash_password
from app.scoring import money, routes

try:  # register P3's tables (audit/approvals) before init_db when they exist
    import app.workflow.approvals  # noqa: F401
    import app.workflow.audit  # noqa: F401
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
