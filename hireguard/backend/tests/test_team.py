"""HR Nexus (Team module): process metrics, knowledge-gap radar, team skills; aggregates only."""
from datetime import date, datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import db as app_db
from app import main  # noqa: F401  registers every schema
from app.auth import core as auth
from app.contracts import ApprovalKind, Role, UserOut
from app.pipeline import demo
from app.team import knowledge_gaps, process_metrics
from app.team import routes as team_routes
from app.workflow import approvals, executor

from test_workflow import make_user


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(app_db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setenv("HG_ANCHOR_LOOP", "0")
    app_db.init_db()
    return tmp_path


def client_for(user: UserOut) -> TestClient:
    app = FastAPI()
    app.include_router(team_routes.router, prefix="/api")
    c = TestClient(app)
    token, csrf = auth.create_session(user.id)
    c.cookies.set(auth.SESSION_COOKIE, token)
    c.headers["X-CSRF-Token"] = csrf
    return c


def ts(day: int) -> str:
    return datetime(2026, 10, day, tzinfo=timezone.utc).isoformat()


def test_process_metrics_on_known_events():
    ev = []
    for i, (short, inv, offer) in enumerate([(3, 4, 12), (5, 7, 15), (2, 3, 9)]):
        ev += [(f"C{i}", "received", ts(1)), (f"C{i}", "shortlisted", ts(1 + short)),
               (f"C{i}", "invited", ts(1 + inv)), (f"C{i}", "offer_sent", ts(1 + offer))]
    ev += [("C9", "received", ts(10)), ("C8", "received", ts(10)), ("C8", "closed", ts(12))]
    m = process_metrics.metrics(ev, now=datetime(2026, 10, 21, tzinfo=timezone.utc))
    tr = {(t["from"], t["to"]): t for t in m["transitions"]}
    assert tr[("received", "shortlisted")]["median_days"] == 3.0
    assert tr[("shortlisted", "invited")]["median_days"] == 1.0
    assert tr[("invited", "interviewed")]["n"] == 0
    assert m["time_to_offer"] == {"n": 3, "median_days": 12.0, "p95_days": 14.7}  # 9, 12, 15 days
    assert m["closed"] == 1 and m["wip"]["received"] == 1 and m["littles_law"]["observed_in_progress"] == 1


def test_live_events_come_from_the_audit_log(db):
    demo.seed_candidates(mode="ground_truth")
    m1, m2 = make_user(Role.hr_manager, "hrm1"), make_user(Role.hr_manager, "hrm2")
    item = approvals.create_item(ApprovalKind.shortlist_commit, "Shortlist",
                                 {"job_id": "JOB-DATA-01", "candidate_ids": ["CAND-002", "CAND-008"]}, created_by="hrm1")
    approvals.decide(item.id, m2, "approve")
    executor.run(item.id, m2)
    m = process_metrics.metrics(process_metrics.events_from_db())
    assert m["reached"]["received"] == 8 and m["reached"]["shortlisted"] == 2


def test_knowledge_gap_radar_hides_small_cells(db):
    a, b = "6. Remote work", "4. Sick leave"
    for _ in range(6):
        knowledge_gaps.record(a, "fr")
    for _ in range(2):
        knowledge_gaps.record(b, "ar")
    for _ in range(5):
        knowledge_gaps.record(None, "en")
    r = knowledge_gaps.radar()
    by = {s["section"]: s for s in r["sections"]}
    assert by[a]["count"] == 6 and by[b] == {"section": b, "count": None, "suppressed": True}
    assert by["3. Public holidays"]["count"] == 0
    assert r["no_match"] == {"count": 5, "share": round(5 / 13, 3)}
    with pytest.raises(ValueError):
        knowledge_gaps.record("99. Not a section", "fr")
    conn = app_db.connect()
    cols = {c["name"] for c in conn.execute("PRAGMA table_info(answer_desk_log)")}
    conn.close()
    assert cols == {"id", "week", "section", "lang"}  # no question text, no employee


def test_team_endpoints_are_hr_only_and_show_counts_not_people(db):
    rec, hrm = make_user(Role.recruiter, "rec1"), make_user(Role.hr_manager, "hrm1")
    assert client_for(rec).get("/api/team/skills").status_code == 403
    r = client_for(hrm).get("/api/team/skills")
    assert r.status_code == 200 and "T-DATA-1" not in r.text and "members" not in r.text
    data = {t["job_id"]: {c["esco_id"]: c["status"] for c in t["coverage"]} for t in r.json()}
    assert data["JOB-DATA-01"]["apache-spark"] == "gap"
    assert client_for(hrm).get("/api/team/process").json()["source"] == "live"
    assert client_for(rec).get("/api/team/knowledge-gaps").status_code == 403
