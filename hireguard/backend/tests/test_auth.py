"""P4 auth + web security tests. Builds a minimal app (auth + security + a probe router)
so it runs even while other layers are still being written."""
import os
import tempfile
from datetime import datetime, timedelta, timezone

os.environ.setdefault("HG_DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from app import security
from app.auth import lockout
from app.auth import routes as auth_routes
from app.auth.core import SESSION_COOKIE, require_roles
from app.contracts import Role
from app.db import connect, init_db
from app.workflow import audit

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
INVALID = {"detail": "Invalid email or password"}


@pytest.fixture()
def client():
    from app.config import DB_PATH
    if not str(DB_PATH).startswith(tempfile.gettempdir()):
        pytest.skip(f"refusing to wipe non-temp DB {DB_PATH}; set HG_DB_PATH in tests/conftest.py")
    init_db()
    conn = connect()
    for table in ("auth_sessions", "auth_users", "auth_throttle"):
        conn.execute(f"DELETE FROM {table}")
    conn.close()
    security.limiter.reset()
    auth_routes.create_user("rec@t.demo", "Rec", Role.recruiter, PW)
    auth_routes.create_user("emp@t.demo", "Emp", Role.employee, PW)
    auth_routes.create_user("adm@t.demo", "Adm", Role.admin, PW)
    return TestClient(make_app())


def login(c, email, password=PW):
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    c.headers["X-CSRF-Token"] = r.json()["csrf"]
    return r.json()["csrf"]


def new_client():
    return TestClient(make_app())


def user_id(email: str) -> str:
    conn = connect()
    try:
        return conn.execute("SELECT id FROM auth_users WHERE email = ?", (email,)).fetchone()["id"]
    finally:
        conn.close()


def shift_sessions(column: str, delta: timedelta):
    conn = connect()
    conn.execute(f"UPDATE auth_sessions SET {column} = ?", ((datetime.now(timezone.utc) + delta).isoformat(),))
    conn.close()

# ---------------------------------------------------------------- login


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
    assert a.json() == b.json() == INVALID


def test_lockout_after_5_failures_is_invisible_and_expires(client):
    for _ in range(5):
        assert client.post("/api/auth/login", json={"email": "rec@t.demo", "password": "x"}).json() == INVALID
    # locked: even the right password is refused, with exactly the answer a wrong password gets
    r = client.post("/api/auth/login", json={"email": "rec@t.demo", "password": PW})
    assert r.status_code == 401 and r.json() == INVALID
    assert any(e.action == "auth.lockout" and e.object_id == "rec@t.demo" for e in audit.list_entries(50))

    conn = connect()  # the 15-minute window passes
    conn.execute("UPDATE auth_throttle SET locked_until = ? WHERE key = 'acct:rec@t.demo'",
                 ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),))
    conn.close()
    assert client.post("/api/auth/login", json={"email": "rec@t.demo", "password": PW}).status_code == 200


def test_unknown_emails_lock_the_same_way(client):
    for _ in range(6):
        r = client.post("/api/auth/login", json={"email": "ghost@t.demo", "password": "x"})
        assert r.status_code == 401 and r.json() == INVALID


def test_ip_lockout_answers_429_with_retry_after(client, monkeypatch):
    monkeypatch.setattr(lockout, "IP_MAX_FAILED", 3)
    for i in range(3):  # password spraying: a different account each time
        assert client.post("/api/auth/login", json={"email": f"v{i}@t.demo", "password": "x"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": "rec@t.demo", "password": PW})
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0


def test_password_policy(client):
    login(client, "adm@t.demo")
    base = {"display_name": "N", "role": "recruiter"}
    for pw, why in (("short", "at least 12"), ("password1234", "too common"), ("aaaaaaaaaaaaaa", "too common"),
                    ("nadia.ben-ali-2026", "email")):
        r = client.post("/api/auth/users", json=base | {"email": "nadia.ben-ali@t.demo", "password": pw})
        assert r.status_code == 422 and why in r.json()["detail"], (pw, r.json())
    ok = client.post("/api/auth/users", json=base | {"email": "n@t.demo", "password": "a-long-password-1"})
    assert ok.status_code == 201

# ---------------------------------------------------------------- sessions


def test_me_sends_role_permissions_and_idle_timeout(client):
    login(client, "rec@t.demo")
    me = client.get("/api/auth/me").json()
    assert me["role"] == "recruiter" and "candidates.read" in me["permissions"]
    assert "users.manage" not in me["permissions"] and me["idle_timeout_s"] == 30 * 60 and me["csrf"]


def test_idle_timeout(client):
    login(client, "rec@t.demo")
    shift_sessions("last_seen", -timedelta(minutes=31))
    r = client.get("/api/auth/me")
    assert r.status_code == 401 and r.json()["detail"] == "session expired"
    conn = connect()
    assert conn.execute("SELECT COUNT(*) FROM auth_sessions").fetchone()[0] == 0  # removed, not just refused
    conn.close()


def test_activity_keeps_the_session_alive(client):
    login(client, "rec@t.demo")
    shift_sessions("last_seen", -timedelta(minutes=29))
    assert client.get("/api/auth/me").status_code == 200  # touches last_seen
    conn = connect()
    last = datetime.fromisoformat(conn.execute("SELECT last_seen FROM auth_sessions").fetchone()[0])
    conn.close()
    assert datetime.now(timezone.utc) - last < timedelta(seconds=5)


def test_absolute_expiry(client):
    login(client, "rec@t.demo")
    shift_sessions("expires_at", -timedelta(seconds=1))
    assert client.get("/api/auth/me").status_code == 401


def test_login_rotates_the_session_token(client):
    login(client, "rec@t.demo")
    planted = client.cookies[SESSION_COOKIE]
    login(client, "rec@t.demo")
    assert client.cookies[SESSION_COOKIE] != planted
    other = new_client()
    other.cookies.set(SESSION_COOKIE, planted)
    assert other.get("/api/auth/me").status_code == 401


def test_logout_kills_session(client):
    login(client, "rec@t.demo")
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_logout_all_kills_every_session_of_the_user(client):
    laptop, phone, colleague = client, new_client(), new_client()
    login(laptop, "rec@t.demo")
    login(phone, "rec@t.demo")
    login(colleague, "emp@t.demo")
    r = laptop.post("/api/auth/logout-all")
    assert r.status_code == 200 and r.json()["sessions_closed"] == 2
    assert laptop.get("/api/auth/me").status_code == 401 and phone.get("/api/auth/me").status_code == 401
    assert colleague.get("/api/auth/me").status_code == 200

# ---------------------------------------------------------------- user administration


def test_deactivation_and_role_change_kill_sessions(client):
    rec, emp = new_client(), new_client()
    login(rec, "rec@t.demo")
    login(emp, "emp@t.demo")
    login(client, "adm@t.demo")

    r = client.patch(f"/api/auth/users/{user_id('rec@t.demo')}", json={"active": False})
    assert r.status_code == 200 and r.json()["active"] is False
    assert rec.get("/api/auth/me").status_code == 401
    assert rec.post("/api/auth/login", json={"email": "rec@t.demo", "password": PW}).json() == INVALID

    r = client.patch(f"/api/auth/users/{user_id('emp@t.demo')}", json={"role": "hr_manager"})
    assert r.status_code == 200 and r.json()["role"] == "hr_manager"
    assert emp.get("/api/auth/me").status_code == 401
    login(emp, "emp@t.demo")
    assert emp.get("/api/auth/me").json()["role"] == "hr_manager"

    events = [e for e in audit.list_entries(50) if e.action == "auth.user_update"]
    assert {"role", "sessions_closed"} <= set(events[0].details) and events[1].details["active"] is False


def test_admin_cannot_demote_or_deactivate_themselves(client):
    login(client, "adm@t.demo")
    me = user_id("adm@t.demo")
    assert client.patch(f"/api/auth/users/{me}", json={"role": "hr_manager"}).status_code == 409
    assert client.patch(f"/api/auth/users/{me}", json={"active": False}).status_code == 409
    assert client.patch("/api/auth/users/USR-nope", json={"active": False}).status_code == 404


def test_reset_password_and_unlock(client):
    rec = new_client()
    login(rec, "rec@t.demo")
    for _ in range(5):
        new_client().post("/api/auth/login", json={"email": "rec@t.demo", "password": "x"})
    login(client, "adm@t.demo")
    listed = {u["email"]: u for u in client.get("/api/auth/users").json()}
    assert listed["rec@t.demo"]["locked_until"] and listed["rec@t.demo"]["last_login_at"]

    r = client.post(f"/api/auth/users/{user_id('rec@t.demo')}/reset-password")
    temp = r.json()["password"]
    assert r.status_code == 200 and len(temp) >= 20
    assert rec.get("/api/auth/me").status_code == 401  # sessions closed
    assert new_client().post("/api/auth/login", json={"email": "rec@t.demo", "password": PW}).status_code == 401
    login(new_client(), "rec@t.demo", temp)  # lockout cleared too
    assert not any(temp in str(e.details) for e in audit.list_entries(100))


def test_users_list_includes_inactive_accounts(client):
    login(client, "adm@t.demo")
    client.patch(f"/api/auth/users/{user_id('emp@t.demo')}", json={"active": False})
    listed = {u["email"]: u["active"] for u in client.get("/api/auth/users").json()}
    assert listed == {"adm@t.demo": True, "rec@t.demo": True, "emp@t.demo": False}

# ---------------------------------------------------------------- guards, CSRF, audit, hardening


def test_csrf_required_on_mutations(client):
    csrf = login(client, "rec@t.demo")
    del client.headers["X-CSRF-Token"]
    assert client.post("/api/recruiter-only").status_code == 403
    assert client.post("/api/recruiter-only", headers={"X-CSRF-Token": "forged"}).status_code == 403
    assert client.post("/api/recruiter-only", headers={"X-CSRF-Token": csrf}).status_code == 200


def test_role_checks(client):
    login(client, "emp@t.demo")
    assert client.post("/api/recruiter-only").status_code == 403
    assert client.get("/api/auth/users").status_code == 403


def test_admin_creates_user_with_strong_password(client):
    login(client, "adm@t.demo")
    weak = client.post("/api/auth/users", json={"email": "n@t.demo", "display_name": "N", "role": "recruiter",
                                                 "password": "short"})
    assert weak.status_code == 422
    ok = client.post("/api/auth/users", json={"email": "n@t.demo", "display_name": "N", "role": "recruiter",
                                              "password": "a-long-password-1"})
    assert ok.status_code == 201
    assert any(u["email"] == "n@t.demo" for u in client.get("/api/auth/users").json())


def test_auth_events_are_audited_without_secrets(client):
    client.post("/api/auth/login", json={"email": "rec@t.demo", "password": "wrong-password-xyz"})
    login(client, "rec@t.demo")
    client.post("/api/recruiter-only")
    client.post("/api/auth/logout")
    actions = [e.action for e in audit.list_entries(20)]
    for a in ("auth.login_failed", "auth.login", "auth.logout"):
        assert a in actions
    dump = str([e.details for e in audit.list_entries(50)])
    assert PW not in dump and "wrong-password-xyz" not in dump


def test_unauthenticated_is_401(client):
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


def test_client_ip_trusts_forwarded_for_only_from_listed_proxies(monkeypatch):
    import ipaddress
    monkeypatch.setattr(security, "_PROXIES", [ipaddress.ip_network("10.0.0.0/8")])
    assert security.client_ip("203.0.113.9", "1.2.3.4") == "203.0.113.9"           # not a proxy: header ignored
    assert security.client_ip("10.0.0.2", "1.2.3.4") == "1.2.3.4"                    # proxy: real client
    assert security.client_ip("10.0.0.2", "6.6.6.6, 1.2.3.4, 10.0.0.7") == "1.2.3.4"  # spoofed left-most hop ignored
    assert security.client_ip("10.0.0.2", "not-an-ip") == "10.0.0.2"                 # garbage: fall back to peer
    assert security.client_ip("10.0.0.2", None) == "10.0.0.2"


def test_session_from_before_the_upgrade_starts_its_idle_clock(client):
    login(client, "rec@t.demo")
    conn = connect()
    conn.execute("UPDATE auth_sessions SET last_seen = NULL")  # what the migration leaves behind
    conn.close()
    assert client.get("/api/auth/me").status_code == 200
    conn = connect()
    assert conn.execute("SELECT last_seen FROM auth_sessions").fetchone()[0] is not None
    conn.close()
    shift_sessions("last_seen", -timedelta(minutes=31))
    assert client.get("/api/auth/me").status_code == 401


def test_relative_paths_resolve_against_the_project_root(monkeypatch):
    from app import config
    monkeypatch.setenv("HG_X_PATH", "backend/hireguard.db")
    assert config._path("HG_X_PATH", config.ROOT / "d") == config.ROOT / "backend" / "hireguard.db"
    monkeypatch.setenv("HG_X_PATH", str(config.ROOT / "abs.db"))
    assert config._path("HG_X_PATH", config.ROOT / "d") == config.ROOT / "abs.db"
