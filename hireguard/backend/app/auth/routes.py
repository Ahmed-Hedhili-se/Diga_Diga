"""Auth endpoints (P4). Prefix /api/auth."""
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ..config import COOKIE_SECURE, SESSION_TTL_MIN
from ..contracts import Role, UserOut
from ..db import connect
from .core import (
    SESSION_COOKIE,
    _token_hash,
    create_session,
    current_user,
    destroy_session,
    hash_password,
    require_roles,
    verify_password,
)

router = APIRouter()

MAX_FAILED = 5
LOCK_MINUTES = 15
# Constant-time-ish path for unknown emails: verify against a throwaway hash
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    display_name: str = Field(min_length=1, max_length=80)
    role: Role
    password: str = Field(min_length=12, max_length=256)


def _row_to_user(row: sqlite3.Row) -> UserOut:
    return UserOut(id=row["id"], email=row["email"], display_name=row["display_name"], role=Role(row["role"]))


def _set_cookie(resp: Response, token: str):
    resp.set_cookie(
        SESSION_COOKIE, token, max_age=SESSION_TTL_MIN * 60, httponly=True,
        secure=COOKIE_SECURE, samesite="strict", path="/api",
    )


@router.post("/login")
def login(body: LoginIn, response: Response):
    email = body.email.strip().lower()
    now = datetime.now(timezone.utc)
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM auth_users WHERE email = ?", (email,)).fetchone()
        if not row or not row["active"]:
            verify_password(body.password, _DUMMY_HASH)
            raise HTTPException(401, "invalid credentials")
        if row["locked_until"] and datetime.fromisoformat(row["locked_until"]) > now:
            raise HTTPException(423, "account temporarily locked")
        if not verify_password(body.password, row["pw_hash"]):
            failed = row["failed_logins"] + 1
            locked = (now + timedelta(minutes=LOCK_MINUTES)).isoformat() if failed >= MAX_FAILED else None
            conn.execute(
                "UPDATE auth_users SET failed_logins = ?, locked_until = ? WHERE id = ?",
                (0 if locked else failed, locked, row["id"]),
            )
            raise HTTPException(423 if locked else 401, "account temporarily locked" if locked else "invalid credentials")
        conn.execute("UPDATE auth_users SET failed_logins = 0, locked_until = NULL WHERE id = ?", (row["id"],))
    finally:
        conn.close()
    token, csrf = create_session(row["id"])
    _set_cookie(response, token)
    return {"user": _row_to_user(row), "csrf": csrf}


@router.post("/logout")
def logout(request: Request, response: Response, user: UserOut = Depends(current_user)):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        destroy_session(token)
    response.delete_cookie(SESSION_COOKIE, path="/api")
    return {"ok": True}


@router.get("/me")
def me(request: Request, user: UserOut = Depends(current_user)):
    conn = connect()
    try:
        row = conn.execute(
            "SELECT csrf FROM auth_sessions WHERE token_hash = ?",
            (_token_hash(request.cookies[SESSION_COOKIE]),),
        ).fetchone()
    finally:
        conn.close()
    return {"user": user, "csrf": row["csrf"]}


@router.get("/users", response_model=list[UserOut])
def list_users(_: UserOut = Depends(require_roles(Role.admin))):
    conn = connect()
    try:
        rows = conn.execute("SELECT * FROM auth_users WHERE active = 1 ORDER BY email").fetchall()
    finally:
        conn.close()
    return [_row_to_user(r) for r in rows]


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


@router.post("/users", response_model=UserOut, status_code=201)
def add_user(body: UserCreate, _: UserOut = Depends(require_roles(Role.admin))):
    return create_user(body.email, body.display_name, body.role, body.password)
