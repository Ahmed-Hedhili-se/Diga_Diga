"""P4 auth + web security tests. Builds a minimal app (auth + security + a probe router)
so it runs even while other layers are still being written."""
import os
import tempfile

os.environ.setdefault("HG_DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from app import security
from app.auth import routes as auth_routes
from app.auth.core import require_roles
from app.contracts import Role
from app.db import connect, init_db

probe = APIRouter()


@probe.post("/recruiter-only")
def recruiter_only(user=Depends(require_roles(Role.recruiter, Role.hr_manager))):
    return {"ok": True, "role": user.role}


def make_app():
    app = FastAPI()
    security.install(app)
    app.include_router(auth_routes.router, prefix="/api/auth")
    app.include_router(probe, prefix="/api")
    return app


PW = "correct-horse-battery"


@pytest.fixture()
def client():
    from app.config import DB_PATH
    if not str(DB_PATH).startswith(tempfile.gettempdir()):
        pytest.skip(f"refusing to wipe non-temp DB {DB_PATH}; set HG_DB_PATH in tests/conftest.py")
    init_db()
    conn = connect()
    conn.execute("DELETE FROM auth_sessions")
    conn.execute("DELETE FROM auth_users")
    conn.close()
    security.limiter.reset()
    auth_routes.create_user("rec@t.demo", "Rec", Role.recruiter, PW)
    auth_routes.create_user("emp@t.demo", "Emp", Role.employee, PW)
    auth_routes.create_user("adm@t.demo", "Adm", Role.admin, PW)
    return TestClient(make_app())


def login(c, email):
    r = c.post("/api/auth/login", json={"email": email, "password": PW})
    assert r.status_code == 200, r.text
    return r.json()["csrf"]


def test_login_sets_httponly_strict_cookie(client):
    r = client.post("/api/auth/login", json={"email": "rec@t.demo", "password": PW})
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "recruiter"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert client.get("/api/auth/me").json()["user"]["email"] == "rec@t.demo"


def test_wrong_password_and_unknown_user_look_same(client):
    a = client.post("/api/auth/login", json={"email": "rec@t.demo", "password": "nope"})
    b = client.post("/api/auth/login", json={"email": "ghost@t.demo", "password": "nope"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_lockout_after_5_failures(client):
    for _ in range(4):
        assert client.post("/api/auth/login", json={"email": "rec@t.demo", "password": "x"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "rec@t.demo", "password": "x"}).status_code == 423
    # even the right password is refused while locked
    assert client.post("/api/auth/login", json={"email": "rec@t.demo", "password": PW}).status_code == 423


def test_csrf_required_on_mutations(client):
    csrf = login(client, "rec@t.demo")
    assert client.post("/api/recruiter-only").status_code == 403
    assert client.post("/api/recruiter-only", headers={"X-CSRF-Token": "forged"}).status_code == 403
    assert client.post("/api/recruiter-only", headers={"X-CSRF-Token": csrf}).status_code == 200


def test_role_checks(client):
    csrf = login(client, "emp@t.demo")
    assert client.post("/api/recruiter-only", headers={"X-CSRF-Token": csrf}).status_code == 403
    assert client.get("/api/auth/users").status_code == 403


def test_admin_creates_user_with_strong_password(client):
    csrf = login(client, "adm@t.demo")
    h = {"X-CSRF-Token": csrf}
    weak = client.post("/api/auth/users", headers=h,
                       json={"email": "n@t.demo", "display_name": "N", "role": "recruiter", "password": "short"})
    assert weak.status_code == 422
    ok = client.post("/api/auth/users", headers=h,
                     json={"email": "n@t.demo", "display_name": "N", "role": "recruiter", "password": "a-long-password-1"})
    assert ok.status_code == 201
    assert any(u["email"] == "n@t.demo" for u in client.get("/api/auth/users").json())


def test_unauthenticated_is_401(client):
    assert client.get("/api/auth/me").status_code == 401


def test_logout_kills_session(client):
    csrf = login(client, "rec@t.demo")
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_security_headers_present(client):
    r = client.get("/api/auth/me")
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert "script-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["cross-origin-opener-policy"] == "same-origin"


def test_login_rate_limited(client):
    codes = [client.post("/api/auth/login", json={"email": "ghost@t.demo", "password": "x"}).status_code
             for _ in range(12)]
    assert 429 in codes


def test_body_size_cap(client):
    r = client.post("/api/auth/login", content=b"x" * (300 * 1024), headers={"content-type": "application/json"})
    assert r.status_code == 413
