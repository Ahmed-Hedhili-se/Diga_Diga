"""RBAC proof (P4): every route x every role matches auth/permissions.py, plus IDOR and separation of duties.

Cases are generated from FastAPI's route table, so a new route that is missing from ROUTE_PERMISSIONS, or is
unprotected, or is guarded by roles that disagree with the matrix, fails here.
"""
import re

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import db as app_db
from app import security
from app.auth import core as auth
from app.auth.permissions import AUTHENTICATED, PUBLIC, ROLE_PERMISSIONS, ROUTE_PERMISSIONS, Permission, roles_with
from app.contracts import Role
from app.main import app
from app.workflow import approvals, documents, employee_questions
from test_workflow import make_user

ROLES = list(Role)
STATE_CHANGING = {"POST", "PUT", "PATCH", "DELETE"}


def _routes() -> list[tuple[str, str, APIRoute]]:
    return [(m, r.path, r) for r in app.routes if isinstance(r, APIRoute) for m in sorted(r.methods)]


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "X-PROBE-1", path)


def _guards(route: APIRoute) -> list:
    out, stack = [], list(route.dependant.dependencies)
    while stack:
        d = stack.pop()
        out.append(d.call)
        stack.extend(d.dependencies)
    return out


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(app_db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setenv("HG_ANCHOR_LOOP", "0")
    monkeypatch.setitem(security.LIMITS, "general", (100_000, 60))  # the matrix sends a few hundred requests
    security.limiter.reset()
    app_db.init_db()
    return tmp_path


@pytest.fixture
def clients(db):
    """One logged-in client per role (session + CSRF header)."""
    out = {}
    for role in ROLES:
        user = make_user(role, f"u-{role.value}")
        c = TestClient(app)
        token, csrf = auth.create_session(user.id)
        c.cookies.set(auth.SESSION_COOKIE, token)
        c.headers["X-CSRF-Token"] = csrf
        out[role] = c
    return out

# ---------------------------------------------------------------- the matrix


def test_route_table_and_matrix_cover_each_other():
    live = {(m, p) for m, p, _ in _routes()}
    assert live - set(ROUTE_PERMISSIONS) == set(), "routes without an entry in ROUTE_PERMISSIONS"
    assert set(ROUTE_PERMISSIONS) - live == set(), "ROUTE_PERMISSIONS entries for routes that no longer exist"


@pytest.mark.parametrize("method,path,route", _routes(), ids=[f"{m} {p}" for m, p, _ in _routes()])
def test_each_route_is_guarded_as_the_matrix_says(method, path, route):
    need = ROUTE_PERMISSIONS[(method, path)]
    calls = _guards(route)
    guards = [c for c in calls if hasattr(c, "roles")]
    if need == PUBLIC:
        assert auth.current_user not in calls and not guards
    elif need == AUTHENTICATED:
        assert auth.current_user in calls and not guards
    else:
        assert len(guards) == 1, f"{method} {path}: expected one role/permission guard, found {len(guards)}"
        assert guards[0].roles == roles_with(need), (
            f"{method} {path} allows {sorted(r.value for r in guards[0].roles)}, "
            f"matrix says {sorted(r.value for r in roles_with(need))} for {need.value}")


def test_every_denied_role_gets_403_and_every_allowed_role_gets_through(clients):
    checked = 0
    for method, path, _ in _routes():
        need = ROUTE_PERMISSIONS[(method, path)]
        if not isinstance(need, Permission):
            continue
        url = _concrete(path)
        allowed = roles_with(need)
        for role in ROLES:
            if role in allowed and method in STATE_CHANGING:
                continue  # allowed writes are exercised by each layer's own tests (no side effects here)
            r = clients[role].request(method, url, json={} if method in STATE_CHANGING else None)
            if role in allowed:
                assert r.status_code not in (401, 403), (role.value, method, path, r.status_code, r.text)
            else:
                assert r.status_code == 403, (role.value, method, path, r.status_code, r.text)
            checked += 1
    assert checked > 100


def test_anonymous_gets_401_everywhere_but_public_routes(db):
    c = TestClient(app)
    for method, path, _ in _routes():
        if ROUTE_PERMISSIONS[(method, path)] == PUBLIC:
            continue
        r = c.request(method, _concrete(path), json={} if method in STATE_CHANGING else None)
        assert r.status_code == 401, (method, path, r.status_code)


def test_state_changing_routes_need_csrf_even_for_allowed_roles(clients):
    for method, path, _ in _routes():
        need = ROUTE_PERMISSIONS[(method, path)]
        if method not in STATE_CHANGING or need == PUBLIC:
            continue
        role = next(r for r in ROLES if need == AUTHENTICATED or r in roles_with(need))
        c = clients[role]
        r = c.request(method, _concrete(path), json={}, headers={"X-CSRF-Token": "forged"})
        assert r.status_code == 403 and r.json()["detail"] == "csrf check failed", (method, path, r.status_code)


def test_me_sends_the_same_matrix_to_the_frontend(clients):
    for role, c in clients.items():
        body = c.get("/api/auth/me").json()
        assert body["role"] == role.value
        assert set(body["permissions"]) == {p.value for p in ROLE_PERMISSIONS[role]}


def test_high_risk_kinds_are_decided_only_by_holders_of_the_high_risk_permission():
    for kind, deciders in approvals.DECIDERS.items():
        assert set(deciders) <= roles_with(Permission.approvals_decide_high_risk), kind

# ---------------------------------------------------------------- separation of duties


def test_admin_cannot_read_candidates_or_decide_hr_items(clients):
    adm = clients[Role.admin]
    for path in ("/api/candidates", "/api/candidates/CAND-001", "/api/candidates/CAND-001/pdf", "/api/jobs",
                 "/api/inbox", "/api/approvals", "/api/employee-questions"):
        assert adm.get(path).status_code == 403, path
    item = approvals.create_item("email_send", "x", {"to": "a@b.example", "recipient_verified": True},
                                 created_by="system")
    assert adm.post(f"/api/approvals/{item.id}/decision", json={"decision": "approve"}).status_code == 403
    assert adm.post(f"/api/executor/run/{item.id}").status_code == 403
    assert approvals.get_item(item.id).status == "pending"
    assert adm.get("/api/auth/users").status_code == 200


def test_recruiter_and_employee_cannot_reach_admin_endpoints(clients):
    for role in (Role.recruiter, Role.employee, Role.hr_manager):
        c = clients[role]
        assert c.get("/api/auth/users").status_code == 403
        assert c.post("/api/auth/users", json={}).status_code == 403
        assert c.patch("/api/auth/users/u-admin", json={"role": "employee"}).status_code == 403
        assert c.post("/api/audit/anchor").status_code == 403


def test_denials_are_audited(clients):
    from app.workflow import audit
    clients[Role.employee].get("/api/erp/status")          # require_permission route
    clients[Role.employee].get("/api/security/findings")   # require_roles route (P1)
    denied = [e for e in audit.list_entries(20) if e.action == "auth.permission_denied"]
    assert {e.details["need"] for e in denied} == {"erp.status", "role:admin|hr_manager"}
    assert all(e.actor == "u-employee" and e.details["role"] == "employee" for e in denied)

# ---------------------------------------------------------------- object level (IDOR -> 404, not 403)


def _employee(uid: str):
    user = make_user(Role.employee, uid)
    c = TestClient(app)
    token, csrf = auth.create_session(user.id)
    c.cookies.set(auth.SESSION_COOKIE, token)
    c.headers["X-CSRF-Token"] = csrf
    return user, c


def test_employee_cannot_read_another_employees_document_or_question(db):
    a, ca = _employee("emp-a")
    b, cb = _employee("emp-b")
    conn = app_db.connect()
    conn.execute("INSERT INTO workflow_employees VALUES ('EMP-B','emp-b','Walid Hamdi','Dev','IT','2021-09-15',3400)")
    conn.close()
    item = documents.request_document(b, documents.DocumentRequest(type="work_certificate"))
    doc_id = item["payload"]["document_id"]
    assert cb.get(f"/api/documents/{doc_id}/download").status_code == 409  # B's own doc: exists, not released yet
    assert ca.get(f"/api/documents/{doc_id}/download").status_code == 404  # A: indistinguishable from "no such doc"
    assert ca.get("/api/documents/DOC-does-not-exist/download").status_code == 404

    q = employee_questions.create_employee_question(b, "salary", "my salary question")
    assert cb.get(f"/api/employee-questions/{q['id']}").status_code == 200
    assert ca.get(f"/api/employee-questions/{q['id']}").status_code == 404
    assert all(x["id"] != q["id"] for x in ca.get("/api/employee-questions").json())
