"""Auth core (shared interface, frozen at H0-1). P4 owns this package.

Other modules import `current_user`, `require_roles` or `require_permission`:

    from app.auth.core import require_permission
    from app.auth.permissions import Permission
    @router.post("/x")
    def x(user: UserOut = Depends(require_permission(Permission.candidates_upload))): ...

Sessions: only the SHA-256 of the token is stored. A session ends at its absolute expiry (HG_SESSION_TTL_MIN)
or after HG_SESSION_IDLE_MIN without a request. Every 403 from a guard is audited.
"""
import hashlib
import hmac
import logging
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request

from ..config import SESSION_IDLE_MIN, SESSION_TTL_MIN
from ..contracts import Role, UserOut
from ..db import connect, register_schema
from .permissions import Permission, roles_with

log = logging.getLogger("hireguard.auth")

SESSION_COOKIE = "hg_session"
TOUCH_EVERY = timedelta(seconds=60)  # last_seen is written at most once a minute per session


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
            failed_logins INTEGER NOT NULL DEFAULT 0,   -- legacy, unused: lockouts live in auth_throttle
            locked_until TEXT,                          -- legacy, unused
            last_login_at TEXT
        );
        CREATE TABLE IF NOT EXISTS auth_sessions (
            token_hash TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES auth_users(id),
            csrf TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT,
            last_seen TEXT
        );
        CREATE INDEX IF NOT EXISTS auth_sessions_user ON auth_sessions(user_id);
        """
    )
    # databases created before these columns existed
    _add_column(conn, "auth_users", "last_login_at", "TEXT")
    _add_column(conn, "auth_sessions", "created_at", "TEXT")
    _add_column(conn, "auth_sessions", "last_seen", "TEXT")


def _add_column(conn: sqlite3.Connection, table: str, column: str, decl: str):
    if column not in {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# scrypt cost: OWASP's minimum is N=2^17,r=8,p=1 or an equivalent trade (N=2^16,r=8,p=2: 64 MiB, a few hundred ms).
# The parameters are stored inside each hash, so the cost can rise later and old hashes keep working.
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**16, 8, 2
LEGACY_PARAMS = (2**14, 8, 1)  # hashes written before parameters were stored: "scrypt$<salt>$<dk>"
_MAX_N = 2**20                 # never run a cost taken from the database beyond this (a tampered row cannot hang a login)
_MAXMEM = 2**29


def _scrypt(pw: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(pw.encode(), salt=salt, n=n, r=r, p=p, maxmem=_MAXMEM, dklen=32)


def _parse(stored: str) -> tuple[tuple[int, int, int], bytes, str] | None:
    parts = stored.split("$")
    try:
        if len(parts) == 3 and parts[0] == "scrypt":
            return LEGACY_PARAMS, bytes.fromhex(parts[1]), parts[2]
        if len(parts) == 4 and parts[0] == "scrypt":
            n, r, p = (int(x) for x in parts[1].split(","))
            if n < 2 or n > _MAX_N or n & (n - 1) or not 1 <= r <= 16 or not 1 <= p <= 16:
                return None
            return (n, r, p), bytes.fromhex(parts[2]), parts[3]
    except ValueError:
        pass
    return None


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    dk = _scrypt(pw, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return f"scrypt${SCRYPT_N},{SCRYPT_R},{SCRYPT_P}${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    parsed = _parse(stored)
    if parsed is None:
        return False
    (n, r, p), salt, dk_hex = parsed
    return hmac.compare_digest(_scrypt(pw, salt, n, r, p).hex(), dk_hex)


def needs_rehash(stored: str) -> bool:
    """True for a legacy hash or one made with weaker parameters than today's: rewritten at the next good login."""
    parsed = _parse(stored)
    return parsed is None or parsed[0] != (SCRYPT_N, SCRYPT_R, SCRYPT_P)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(user_id: str) -> tuple[str, str]:
    """Returns (session_token, csrf_token). Only the hash of the session token is stored."""
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    now = _now()
    conn = connect()
    try:
        conn.execute("INSERT INTO auth_sessions (token_hash, user_id, csrf, expires_at, created_at, last_seen) "
                     "VALUES (?,?,?,?,?,?)",
                     (_token_hash(token), user_id, csrf, (now + timedelta(minutes=SESSION_TTL_MIN)).isoformat(),
                      now.isoformat(), now.isoformat()))
    finally:
        conn.close()
    return token, csrf


def destroy_session(token: str):
    conn = connect()
    try:
        conn.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (_token_hash(token),))
    finally:
        conn.close()


def destroy_user_sessions(user_id: str, conn: sqlite3.Connection | None = None) -> int:
    own = conn is None
    conn = conn or connect()
    try:
        return conn.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_id,)).rowcount
    finally:
        if own:
            conn.close()


def current_user(request: Request) -> UserOut:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(401, "not authenticated")
    th, now = _token_hash(token), _now()
    conn = connect()
    try:
        row = conn.execute(
            """SELECT u.id, u.email, u.display_name, u.role, s.csrf, s.expires_at, s.last_seen
               FROM auth_sessions s JOIN auth_users u ON u.id = s.user_id
               WHERE s.token_hash = ? AND u.active = 1""",
            (th,),
        ).fetchone()
        if not row:
            raise HTTPException(401, "session expired")
        last_seen = datetime.fromisoformat(row["last_seen"]) if row["last_seen"] else now
        if datetime.fromisoformat(row["expires_at"]) < now or now - last_seen > timedelta(minutes=SESSION_IDLE_MIN):
            conn.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (th,))
            raise HTTPException(401, "session expired")
        # double-submit CSRF check on every state-changing request
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if not hmac.compare_digest(request.headers.get("X-CSRF-Token", ""), row["csrf"]):
                raise HTTPException(403, "csrf check failed")
        if row["last_seen"] is None or now - last_seen >= TOUCH_EVERY:  # NULL = session from before the upgrade
            conn.execute("UPDATE auth_sessions SET last_seen = ? WHERE token_hash = ?", (now.isoformat(), th))
    finally:
        conn.close()
    request.state.csrf = row["csrf"]
    return UserOut(id=row["id"], email=row["email"], display_name=row["display_name"], role=Role(row["role"]))


def _audit_denied(user: UserOut, request: Request, need: str):
    try:
        from ..workflow import audit
        audit.append(user.id, "auth.permission_denied", "route", request.url.path[:200],
                     {"method": request.method, "role": user.role.value, "need": need})
    except Exception as e:  # a failed audit write must not turn a 403 into a 500
        log.warning("could not audit permission denial: %s", e)


def _guard(allowed: frozenset[Role], need: str):
    def dep(request: Request, user: UserOut = Depends(current_user)) -> UserOut:
        if user.role not in allowed:
            _audit_denied(user, request, need)
            raise HTTPException(403, "forbidden")
        return user

    dep.roles = allowed  # read by tests/test_rbac.py
    return dep


def require_roles(*roles: Role):
    return _guard(frozenset(roles), "role:" + "|".join(sorted(r.value for r in roles)))


def require_permission(*perms: Permission):
    dep = _guard(roles_with(*perms), "+".join(p.value for p in perms))
    dep.permissions = frozenset(perms)
    return dep
