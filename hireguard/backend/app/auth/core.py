"""Auth core (shared interface, frozen at H0-1). P4 owns this package.

Other modules only import `current_user` and `require_roles`:

    from app.auth.core import require_roles
    @router.post("/x")
    def x(user: UserOut = Depends(require_roles(Role.recruiter, Role.hr_manager))): ...
"""
import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request

from ..config import SESSION_TTL_MIN
from ..contracts import Role, UserOut
from ..db import connect, register_schema

SESSION_COOKIE = "hg_session"


@register_schema
def _schema(conn: sqlite3.Connection):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS auth_users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('recruiter','hr_manager','employee','admin')),
            pw_hash TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            failed_logins INTEGER NOT NULL DEFAULT 0,
            locked_until TEXT
        );
        CREATE TABLE IF NOT EXISTS auth_sessions (
            token_hash TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES auth_users(id),
            csrf TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );
        """
    )


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, salt_hex, dk_hex = stored.split("$")
    except ValueError:
        return False
    dk = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=32)
    return hmac.compare_digest(dk.hex(), dk_hex)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(user_id: str) -> tuple[str, str]:
    """Returns (session_token, csrf_token). Only the hash of the session token is stored."""
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    exp = (datetime.now(timezone.utc) + timedelta(minutes=SESSION_TTL_MIN)).isoformat()
    conn = connect()
    try:
        conn.execute("INSERT INTO auth_sessions VALUES (?,?,?,?)", (_token_hash(token), user_id, csrf, exp))
    finally:
        conn.close()
    return token, csrf


def destroy_session(token: str):
    conn = connect()
    try:
        conn.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (_token_hash(token),))
    finally:
        conn.close()


def current_user(request: Request) -> UserOut:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(401, "not authenticated")
    conn = connect()
    try:
        row = conn.execute(
            """SELECT u.id, u.email, u.display_name, u.role, s.csrf, s.expires_at
               FROM auth_sessions s JOIN auth_users u ON u.id = s.user_id
               WHERE s.token_hash = ? AND u.active = 1""",
            (_token_hash(token),),
        ).fetchone()
    finally:
        conn.close()
    if not row or datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
        raise HTTPException(401, "session expired")
    # double-submit CSRF check on every state-changing request
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        sent = request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(sent, row["csrf"]):
            raise HTTPException(403, "csrf check failed")
    return UserOut(id=row["id"], email=row["email"], display_name=row["display_name"], role=Role(row["role"]))


def require_roles(*roles: Role):
    allowed = set(roles)

    def dep(user: UserOut = Depends(current_user)) -> UserOut:
        if user.role not in allowed:
            raise HTTPException(403, "forbidden for role")
        return user

    return dep
