"""Auth endpoints (P4). Prefix /api/auth.

Every auth event is audited through workflow.audit (never a password, hash or token in the details).
"""
import secrets
import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ..config import COOKIE_SECURE, SESSION_IDLE_MIN, SESSION_TTL_MIN
from ..contracts import Role, UserOut
from ..db import connect, tx
from ..workflow import audit  # also registers the audit_log schema for auth-only apps
from . import lockout, passwords
from .core import (
    SESSION_COOKIE,
    create_session,
    current_user,
    destroy_session,
    destroy_user_sessions,
    hash_password,
    require_permission,
    verify_password,
)
from .permissions import Permission, matrix, permissions_for

router = APIRouter()

MAX_FAILED = lockout.ACCOUNT_MAX_FAILED  # read by tests/test_pentest_p3.py
INVALID = "Invalid email or password"
# Unknown and inactive accounts are checked against a throwaway hash, so they cost the same time as real ones.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))

USERS = require_permission(Permission.users_manage)


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class UserCreate(BaseModel, extra="forbid"):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    display_name: str = Field(min_length=1, max_length=80)
    role: Role
    password: str = Field(min_length=1, max_length=256)


class UserPatch(BaseModel, extra="forbid"):
    role: Role | None = None
    active: bool | None = None
    unlock: bool = False


class UserAdminOut(UserOut):
    active: bool
    last_login_at: str | None = None
    locked_until: str | None = None


def _audit(actor: str, action: str, object_id: str, details: dict, conn: sqlite3.Connection | None = None):
    audit.append(actor, action, "auth_user", object_id, details, conn=conn)


def _row_to_user(row: sqlite3.Row) -> UserOut:
    return UserOut(id=row["id"], email=row["email"], display_name=row["display_name"], role=Role(row["role"]))


def _row_to_admin(row: sqlite3.Row, locked: dict[str, str]) -> UserAdminOut:
    return UserAdminOut(**_row_to_user(row).model_dump(), active=bool(row["active"]),
                        last_login_at=row["last_login_at"], locked_until=locked.get(row["email"]))


def _set_cookie(resp: Response, token: str):
    resp.set_cookie(
        SESSION_COOKIE, token, max_age=SESSION_TTL_MIN * 60, httponly=True,
        secure=COOKIE_SECURE, samesite="strict", path="/api",
    )


def _session_info(user: UserOut, csrf: str) -> dict:
    return {"user": user, "role": user.role, "permissions": sorted(p.value for p in permissions_for(user.role)),
            "csrf": csrf, "idle_timeout_s": SESSION_IDLE_MIN * 60}

# ---------------------------------------------------------------- sessions


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response):
    email = body.email.strip().lower()
    ip = request.client.host if request.client else "unknown"
    akey, ikey = lockout.account_key(email), lockout.ip_key(ip)
    now = datetime.now(timezone.utc)

    conn = connect()  # reads first; the slow scrypt check runs outside any write transaction
    try:
        ip_until = lockout.locked_until(conn, ikey, now)
        row = conn.execute("SELECT * FROM auth_users WHERE email = ?", (email,)).fetchone()
        acct_locked = lockout.locked_until(conn, akey, now) is not None
    finally:
        conn.close()
    if ip_until is not None:
        _audit("anonymous", "auth.login_blocked", email, {"ip": ip, "reason": "ip_locked"})
        raise HTTPException(429, "Too many failed sign-ins from this network. Try again later.",
                            headers={"Retry-After": str(int((ip_until - now).total_seconds()) + 1)})

    usable = bool(row and row["active"])
    ok = verify_password(body.password, row["pw_hash"] if usable else _DUMMY_HASH) and usable and not acct_locked

    with tx() as conn:
        if ok:
            lockout.clear(conn, akey)
            conn.execute("UPDATE auth_users SET last_login_at = ? WHERE id = ?", (now.isoformat(), row["id"]))
            _audit(row["id"], "auth.login", row["id"], {"ip": ip}, conn=conn)
        else:
            reason = "locked" if acct_locked else "bad_password" if usable else "unknown_or_inactive"
            _audit("anonymous", "auth.login_failed", email, {"ip": ip, "reason": reason}, conn=conn)
            if not acct_locked:  # attempts during a lock don't extend it
                if lockout.record_failure(conn, akey, MAX_FAILED, now):
                    _audit("system:auth", "auth.lockout", email, {"scope": "account", "ip": ip}, conn=conn)
                if lockout.record_failure(conn, ikey, lockout.IP_MAX_FAILED, now):
                    _audit("system:auth", "auth.lockout", email, {"scope": "ip", "ip": ip}, conn=conn)
    if not ok:
        # same status and message for wrong password, unknown, inactive and locked accounts (pentest F5)
        raise HTTPException(401, INVALID)

    old = request.cookies.get(SESSION_COOKIE)
    if old:
        destroy_session(old)  # rotate: a session token planted before login is never reused
    token, csrf = create_session(row["id"])
    _set_cookie(response, token)
    return _session_info(_row_to_user(row), csrf)


@router.post("/logout")
def logout(request: Request, response: Response, user: UserOut = Depends(current_user)):
    destroy_session(request.cookies[SESSION_COOKIE])
    response.delete_cookie(SESSION_COOKIE, path="/api")
    _audit(user.id, "auth.logout", user.id, {})
    return {"ok": True}


@router.post("/logout-all")
def logout_all(response: Response, user: UserOut = Depends(current_user)):
    n = destroy_user_sessions(user.id)
    response.delete_cookie(SESSION_COOKIE, path="/api")
    _audit(user.id, "auth.logout_all", user.id, {"sessions": n})
    return {"ok": True, "sessions_closed": n}


@router.get("/me")
def me(request: Request, user: UserOut = Depends(current_user)):
    return _session_info(user, request.state.csrf)


@router.get("/permissions")
def permission_matrix(_: UserOut = Depends(current_user)):
    return matrix()

# ---------------------------------------------------------------- user administration (admin only)


def create_user(email: str, display_name: str, role: Role, password: str) -> UserOut:
    uid = "USR-" + secrets.token_hex(4)
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO auth_users (id, email, display_name, role, pw_hash) VALUES (?,?,?,?,?)",
            (uid, email.strip().lower(), display_name, role.value, hash_password(password)),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(409, "email already exists")
    finally:
        conn.close()
    return UserOut(id=uid, email=email.strip().lower(), display_name=display_name, role=role)


def _load_admin_view(conn: sqlite3.Connection, user_id: str) -> UserAdminOut:
    row = conn.execute("SELECT * FROM auth_users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        raise HTTPException(404, "user not found")
    return _row_to_admin(row, lockout.locked_accounts(conn))


@router.get("/users", response_model=list[UserAdminOut])
def list_users(_: UserOut = Depends(USERS)):
    conn = connect()
    try:
        rows = conn.execute("SELECT * FROM auth_users ORDER BY active DESC, email").fetchall()
        locked = lockout.locked_accounts(conn)
    finally:
        conn.close()
    return [_row_to_admin(r, locked) for r in rows]


@router.post("/users", response_model=UserOut, status_code=201)
def add_user(body: UserCreate, admin: UserOut = Depends(USERS)):
    if msg := passwords.problem(body.password, body.email):
        raise HTTPException(422, msg)
    user = create_user(body.email, body.display_name, body.role, body.password)
    _audit(admin.id, "auth.user_create", user.id, {"role": user.role.value})
    return user


@router.patch("/users/{user_id}", response_model=UserAdminOut)
def update_user(user_id: str, body: UserPatch, admin: UserOut = Depends(USERS)):
    if user_id == admin.id and ((body.role is not None and body.role != admin.role) or body.active is False):
        raise HTTPException(409, "You can't change your own role or deactivate your own account.")
    with tx() as conn:
        row = conn.execute("SELECT * FROM auth_users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(404, "user not found")
        changes: dict = {}
        if body.role is not None and body.role.value != row["role"]:
            conn.execute("UPDATE auth_users SET role = ? WHERE id = ?", (body.role.value, user_id))
            changes["role"] = {"from": row["role"], "to": body.role.value}
        if body.active is not None and int(body.active) != row["active"]:
            conn.execute("UPDATE auth_users SET active = ? WHERE id = ?", (int(body.active), user_id))
            changes["active"] = body.active
        if body.unlock:
            lockout.clear(conn, lockout.account_key(row["email"]))
            changes["unlocked"] = True
        if "role" in changes or changes.get("active") is False:
            changes["sessions_closed"] = destroy_user_sessions(user_id, conn)
        if changes:
            _audit(admin.id, "auth.user_update", user_id, changes, conn=conn)
        return _load_admin_view(conn, user_id)


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: str, admin: UserOut = Depends(USERS)):
    """Generates a temporary password, shown once. Closes the user's sessions and clears any lockout."""
    password = passwords.generate()
    pw_hash = hash_password(password)  # scrypt outside the write transaction
    with tx() as conn:
        row = conn.execute("SELECT email FROM auth_users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(404, "user not found")
        conn.execute("UPDATE auth_users SET pw_hash = ? WHERE id = ?", (pw_hash, user_id))
        lockout.clear(conn, lockout.account_key(row["email"]))
        closed = destroy_user_sessions(user_id, conn)
        _audit(admin.id, "auth.password_reset", user_id, {"sessions_closed": closed}, conn=conn)
    return {"user_id": user_id, "password": password}
