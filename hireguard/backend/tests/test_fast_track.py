"""Fast-track: offer-fit check, offer letters, talent-pool rediscovery. Follow-ups: tests/test_followups.py."""
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import db as app_db
from app import main  # noqa: F401  registers every schema
from app.auth import core as auth
from app.contracts import Role, UserOut
from app.pipeline import demo
from app.pipeline import routes as pipeline_routes
from app.scoring import offer_fit, rediscover
from app.scoring import routes as scoring_routes
from app.workflow import approvals, executor
from app.workflow import routes as workflow_routes

from test_workflow import make_user

TODAY = date(2026, 10, 31)


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(app_db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setenv("HG_ANCHOR_LOOP", "0")
    app_db.init_db()
    return tmp_path


@pytest.fixture
def seeded(db):
    demo.seed_candidates(mode="ground_truth")  # CAND-001..008 for JOB-DATA-01, fictional
    return db


def client_for(user: UserOut) -> TestClient:
    app = FastAPI()
    for r in (pipeline_routes, scoring_routes, workflow_routes):
        app.include_router(r.router, prefix="/api")
    c = TestClient(app)
    token, csrf = auth.create_session(user.id)
    c.cookies.set(auth.SESSION_COOKIE, token)
    c.headers["X-CSRF-Token"] = csrf
    return c


def cond(**kw):
    base = dict(salary_min=3000, notice_weeks=2, work_modes=["hybrid"], commitments_ok=["on_call"])
    return offer_fit.Conditions(**(base | kw))

# ---------------------------------------------------------------- offer fit (pure)


def test_offer_fit_rules():
    t = offer_fit.get_terms("JOB-DATA-01")  # band 2800-3800, hybrid, start by 2027-01-04, on-call
    status = lambda c: offer_fit.offer_fit(t, c, TODAY)["status"]
    assert status(cond()) == "fit"
    assert status(cond(salary_min=4000)) == "negotiable"           # 5% above the band
    assert status(cond(salary_min=4300)) == "mismatch"             # 13% above
    assert status(cond(notice_weeks=12)) == "negotiable"           # 19 days after start_by
    assert status(cond(notice_weeks=16)) == "mismatch"
    assert status(cond(work_modes=["remote"])) == "mismatch"
    assert status(cond(commitments_ok=[])) == "mismatch"           # declines on-call
    assert offer_fit.offer_fit(t, None, TODAY) == {"status": "unknown", "checks": []}


def test_conditions_are_range_checked():
    with pytest.raises(ValidationError):
        cond(salary_min=3500, salary_max=3000)
    with pytest.raises(ValidationError):
        cond(work_modes=[])
    with pytest.raises(ValidationError):
        cond(work_modes=["beach"])


def test_band_coverage_is_job_level():
    t = offer_fit.get_terms("JOB-DATA-01")
    conds = {"A": cond(salary_min=3000), "B": cond(salary_min=4600)}
    assert offer_fit.band_coverage(t, ["A", "B", "C"], conds) == {
        "k": 3, "declared": 2, "within_band": 1, "share": 0.5, "band": [2800, 3800]}

# ---------------------------------------------------------------- API


def test_conditions_never_change_the_score(seeded):
    rec = make_user(Role.recruiter, "rec1")
    c = client_for(rec)
    before = c.post("/api/jobs/JOB-DATA-01/rescore").json()
    assert c.put("/api/candidates/CAND-001/conditions",
                 json={"salary_min": 9000, "work_modes": ["remote"]}).status_code == 200
    assert c.post("/api/jobs/JOB-DATA-01/rescore").json() == before
    fit = c.get("/api/jobs/JOB-DATA-01/offer-fit?k=2").json()
    assert fit["candidates"]["CAND-001"]["status"] == "mismatch"
    assert fit["candidates"]["CAND-007"]["status"] == "unknown"


def test_offer_inside_band_two_approvers_then_sent(seeded):
    rec, m1, m2, m3 = (make_user(Role.recruiter, "rec1"), make_user(Role.hr_manager, "hrm1"),
                       make_user(Role.hr_manager, "hrm2"), make_user(Role.hr_manager, "hrm3"))
    start = (date.today() + timedelta(days=40)).isoformat()
    assert client_for(rec).post("/api/candidates/CAND-001/offer",
                                json={"monthly_salary_tnd": 3200, "start_date": start}).status_code == 403
    r = client_for(m1).post("/api/candidates/CAND-001/offer", json={"monthly_salary_tnd": 4500, "start_date": start})
    assert r.status_code == 422 and "band" in r.text

    r = client_for(m1).post("/api/candidates/CAND-001/offer", json={"monthly_salary_tnd": 3200, "start_date": start})
    assert r.status_code == 200
    item = r.json()
    assert item["kind"] == "offer" and item["required_approvals"] == 2 and "3200 TND" in item["payload"]["email"]["body"]
    again = client_for(m1).post("/api/candidates/CAND-001/offer", json={"monthly_salary_tnd": 3300, "start_date": start})
    assert again.status_code == 422  # one pending offer per candidate

    approvals.decide(item["id"], m2, "approve")
    assert approvals.decide(item["id"], m3, "approve").status == "approved"
    out = executor.run(item["id"], m2)
    assert out["executed"] and out["result"]["to"] == item["payload"]["to"]


def test_rediscovery_needs_valid_consent(seeded):
    rec = make_user(Role.recruiter, "rec1")
    old = datetime(2023, 1, 1, tzinfo=timezone.utc)
    rediscover.add("CAND-001", "JOB-DATA-01", "seed")
    rediscover.add("CAND-002", "JOB-DATA-01", "seed", consent_at=old)      # expired
    rediscover.add("CAND-004", "JOB-DATA-01", "seed")
    assert rediscover.withdraw("CAND-004", "rec1")                          # asked to leave
    # CAND-003 never opted in

    view = client_for(rec).get("/api/jobs/JOB-FS-02/rediscover").json()
    assert [x["candidate_id"] for x in view["candidates"]] == ["CAND-001"]
    assert client_for(rec).get("/api/jobs/JOB-DATA-01/rediscover").json()["candidates"] == []  # already applicants

    items = client_for(rec).post("/api/jobs/JOB-FS-02/rediscover/invite",
                                 json={"candidate_ids": ["CAND-001", "CAND-003"]}).json()
    assert [i["payload"]["candidate_id"] for i in items] == ["CAND-001"]
    assert client_for(rec).post("/api/jobs/JOB-FS-02/rediscover/invite",
                                json={"candidate_ids": ["CAND-001"]}).json() == []  # not twice


def test_upload_with_conditions_and_consent(db):
    rec = make_user(Role.recruiter, "rec1")
    pdf = demo.render_cv(demo.CVS[0])
    form = {"job_id": "JOB-DATA-01", "name": "Test Candidate", "email": "test.candidate@example.tn",
            "salary_min": "3100", "work_modes": "hybrid,onsite", "commitments_ok": "on_call",
            "talent_pool_consent": "true"}
    bad = client_for(rec).post("/api/candidates", data=form | {"work_modes": "beach"},
                               files={"file": ("cv.pdf", pdf, "application/pdf")})
    assert bad.status_code == 422
    r = client_for(rec).post("/api/candidates", data=form, files={"file": ("cv.pdf", pdf, "application/pdf")})
    assert r.status_code == 200
    cid = r.json()["candidate_id"]
    assert offer_fit.get_conditions([cid])[cid].salary_min == 3100
    conn = app_db.connect()
    assert conn.execute("SELECT 1 FROM talent_pool WHERE candidate_id = ?", (cid,)).fetchone()
    conn.close()
