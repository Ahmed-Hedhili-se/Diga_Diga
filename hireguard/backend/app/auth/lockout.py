"""Login lockout: 5 failures per account or HG_LOGIN_IP_MAX_FAILED per IP within 15 minutes -> locked 15 minutes.

Accounts are keyed by the submitted email, so unknown emails lock exactly like real ones. A locked account answers
like a wrong password (pentest F5): the lockout is never visible, so it can't reveal which emails exist.
An IP lock answers 429 with Retry-After, which says nothing about any account.
"""
import sqlite3
from datetime import datetime, timedelta, timezone

from ..config import LOGIN_IP_MAX_FAILED
from ..db import register_schema

ACCOUNT_MAX_FAILED = 5
IP_MAX_FAILED = LOGIN_IP_MAX_FAILED
WINDOW = timedelta(minutes=15)
LOCK = timedelta(minutes=15)


@register_schema
def _schema(conn: sqlite3.Connection):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS auth_throttle (
            key TEXT PRIMARY KEY,          -- 'acct:<email>' or 'ip:<address>'
            failures INTEGER NOT NULL,
            window_start TEXT NOT NULL,
            locked_until TEXT
        );
        """
    )


def account_key(email: str) -> str:
    return f"acct:{email}"


def ip_key(ip: str) -> str:
    return f"ip:{ip}"


def locked_until(conn: sqlite3.Connection, key: str, now: datetime) -> datetime | None:
    r = conn.execute("SELECT locked_until FROM auth_throttle WHERE key = ?", (key,)).fetchone()
    if r and r["locked_until"]:
        until = datetime.fromisoformat(r["locked_until"])
        return until if until > now else None
    return None


def record_failure(conn: sqlite3.Connection, key: str, limit: int, now: datetime) -> bool:
    """Counts one failure. Returns True when this failure locks the key."""
    conn.execute("DELETE FROM auth_throttle WHERE window_start < ? AND (locked_until IS NULL OR locked_until < ?)",
                 ((now - WINDOW).isoformat(), now.isoformat()))  # keeps the table small under spraying
    r = conn.execute("SELECT failures, window_start FROM auth_throttle WHERE key = ?", (key,)).fetchone()
    failures = r["failures"] + 1 if r and datetime.fromisoformat(r["window_start"]) >= now - WINDOW else 1
    start = r["window_start"] if r and failures > 1 else now.isoformat()
    locked = failures >= limit
    conn.execute(
        "INSERT INTO auth_throttle (key, failures, window_start, locked_until) VALUES (?,?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET failures = excluded.failures, window_start = excluded.window_start, "
        "locked_until = excluded.locked_until",
        (key, 0 if locked else failures, now.isoformat() if locked else start,
         (now + LOCK).isoformat() if locked else None))
    return locked


def clear(conn: sqlite3.Connection, key: str):
    conn.execute("DELETE FROM auth_throttle WHERE key = ?", (key,))


def locked_accounts(conn: sqlite3.Connection) -> dict[str, str]:
    """email -> locked_until, for every account locked right now (one query for the Users page)."""
    rows = conn.execute("SELECT key, locked_until FROM auth_throttle WHERE key LIKE 'acct:%' AND locked_until > ?",
                        (datetime.now(timezone.utc).isoformat(),)).fetchall()
    return {r["key"][5:]: r["locked_until"] for r in rows}
