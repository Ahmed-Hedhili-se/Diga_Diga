"""Release gate (Ahmed): built from the live route table, so a new route cannot slip past it.

1. Every route except login and health needs a session (401 without one).
2. Every state-changing route also needs the CSRF header (403 without it, even with a valid session).
3. Every route's roles match the permissions matrix below (docs/architecture.md section 6). A new or
   changed route fails this test until the matrix is updated on purpose, and reviewed.
"""
import re

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import db as app_db
from app.auth import core as auth
from app.auth.core import current_user
from app.contracts import Role
from app.main import app

from test_workflow import make_user

PUBLIC = {("POST", "/api/auth/login"), ("GET", "/api/health")}
ANY = "any signed-in user"

# R recruiter · M hr_manager · E employee · A admin
MATRIX = {
    ("POST", "/api/auth/logout"): ANY,
    ("GET", "/api/auth/me"): ANY,
    ("POST", "/api/auth/logout-all"): ANY,
    ("GET", "/api/auth/permissions"): ANY,
    ("PATCH", "/api/auth/users/{user_id}"): "A",
    ("POST", "/api/auth/users/{user_id}/reset-password"): "A",
    ("GET", "/api/auth/users"): "A",
    ("POST", "/api/auth/users"): "A",
    ("POST", "/api/candidates"): "M R",
    ("GET", "/api/candidates"): "M R",
    ("GET", "/api/candidates/{candidate_id}"): "M R",
    ("GET", "/api/candidates/{candidate_id}/text"): "M R",
    ("GET", "/api/candidates/{candidate_id}/pdf"): "M R",
    ("GET", "/api/security/findings"): "A M",
    ("POST", "/api/answer-desk/ask"): "E M",
    ("GET", "/api/jobs"): "M R",
    ("GET", "/api/jobs/{job_id}/rubric"): "M R",
    ("PUT", "/api/jobs/{job_id}/rubric"): "M",
    ("POST", "/api/jobs/{job_id}/rescore"): "M R",
    ("GET", "/api/jobs/{job_id}/stability"): "M R",
    ("GET", "/api/jobs/{job_id}/team-gaps"): "M R",
    ("GET", "/api/jobs/{job_id}/offer-fit"): "M R",
    ("PUT", "/api/candidates/{candidate_id}/conditions"): "M R",
    ("POST", "/api/candidates/{candidate_id}/offer"): "M",
    ("GET", "/api/jobs/{job_id}/rediscover"): "M R",
    ("POST", "/api/jobs/{job_id}/rediscover/invite"): "M R",
    ("DELETE", "/api/talent-pool/{candidate_id}"): "M R",
    ("POST", "/api/jobs/{job_id}/shortlist"): "M R",
    ("POST", "/api/jobs/{job_id}/candidates/{candidate_id}/status"): "M R",
    ("GET", "/api/erp/status"): "A M R",
    ("GET", "/api/model/status"): "A M R",
    ("GET", "/api/erp/jobs/{job_id}/applicants"): "M R",
    ("POST", "/api/erp/jobs/{job_id}/import"): "M R",
    ("GET", "/api/money"): "A M",
    ("PUT", "/api/money/settings"): "M",
    ("GET", "/api/eval/summary"): "A M",
    ("GET", "/api/eval/fairness"): "A M",
    ("POST", "/api/inbox/ingest"): "A",
    ("GET", "/api/inbox"): "M R",
    ("POST", "/api/inbox/{inbox_id}/release-request"): "M",
    ("GET", "/api/followups/preview"): "M R",
    ("POST", "/api/followups/run"): "M R",
    ("GET", "/api/approvals"): "M R",
    ("POST", "/api/approvals/{item_id}/decision"): "M R",
    ("POST", "/api/approvals/batches/{batch_id}/decision"): "M R",
    ("POST", "/api/executor/run/{item_id}"): "M R",
    ("GET", "/api/reviewer/stats"): "A M",
    ("GET", "/api/approvals/settings"): "M",
    ("PUT", "/api/approvals/settings"): "M",
    ("GET", "/api/approvals/attention"): "A M R",
    ("GET", "/api/calendar/slots"): "M R",
    ("GET", "/api/audit"): "A M",
    ("GET", "/api/audit/verify"): "A M",
    ("POST", "/api/audit/anchor"): "A",
    ("POST", "/api/documents/request"): "E",
    ("GET", "/api/documents/mine"): "E",
    ("GET", "/api/documents/{doc_id}/download"): "E M",
    ("POST", "/api/employee-questions"): "E",
    ("GET", "/api/employee-questions"): "E M",
    ("GET", "/api/employee-questions/{question_id}"): "E M",
    ("POST", "/api/employee-questions/{question_id}/reply"): "M",
    ("POST", "/api/interviews/{interview_id}/scorecard"): "M R",
    ("GET", "/api/interviews/reminders"): "M",
    ("GET", "/api/team/skills"): "A M",
    ("GET", "/api/team/process"): "A M",
    ("GET", "/api/team/knowledge-gaps"): "A M",
}
LETTER = {Role.recruiter: "R", Role.hr_manager: "M", Role.employee: "E", Role.admin: "A"}


def _routes():
    for r in app.routes:
        if isinstance(r, APIRoute):
            for m in sorted(r.methods - {"HEAD", "OPTIONS"}):
                yield m, r.path, r


def _roles(route: APIRoute) -> str:
    for d in route.dependant.dependencies:
        if d.call is current_user:
            return ANY
        code = getattr(d.call, "__code__", None)
        if code and "allowed" in code.co_freevars:
            allowed = d.call.__closure__[code.co_freevars.index("allowed")].cell_contents
            return " ".join(sorted(LETTER[r] for r in allowed))
    return "PUBLIC"


def _url(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "CAND-GATE1", path)  # a well-formed id for every path parameter


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(app_db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setenv("HG_ANCHOR_LOOP", "0")
    app_db.init_db()
    from app import security
    security.limiter.reset()
    return tmp_path


def test_matrix_matches_the_code():
    actual = {(m, p): _roles(r) for m, p, r in _routes() if (m, p) not in PUBLIC}
    assert actual == MATRIX, "route roles changed: update MATRIX and docs/architecture.md section 6 together"


def test_every_route_needs_a_session(db):
    c = TestClient(app)
    open_routes = [(m, p) for m, p, _ in _routes()
                   if (m, p) not in PUBLIC and c.request(m, _url(p)).status_code != 401]
    assert open_routes == []


def test_every_state_change_needs_the_csrf_header(db):
    users = {role: make_user(role, f"gate-{role.value}") for role in Role}
    missing = []
    for m, p, r in _routes():
        if m == "GET" or (m, p) in PUBLIC:
            continue
        roles = _roles(r)
        role = Role.recruiter if roles == ANY else next(k for k, v in LETTER.items() if v in roles.split())
        c = TestClient(app)
        token, _csrf = auth.create_session(users[role].id)
        c.cookies.set(auth.SESSION_COOKIE, token)  # valid session, no X-CSRF-Token header
        res = c.request(m, _url(p))
        if res.status_code != 403 or "csrf" not in res.text:
            missing.append((m, p, res.status_code))
    assert missing == []
