"""Mock recruiter calendar: 45-min slots on business days, 09:00-16:00 Africa/Tunis (UTC+1)."""
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from ..db import connect, register_schema
from .common import now

TUNIS = timezone(timedelta(hours=1))
SLOT_MIN = 45


@register_schema
def _schema(conn: sqlite3.Connection):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS calendar_slots (
            id TEXT PRIMARY KEY,
            recruiter_id TEXT NOT NULL,
            start TEXT NOT NULL,
            end TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('free','busy','booked')),
            candidate_id TEXT
        );
        CREATE INDEX IF NOT EXISTS calendar_slots_free ON calendar_slots(recruiter_id, status, start);
        """
    )


def _ensure_slots(conn, recruiter_id: str, days: int = 10):
    if conn.execute("SELECT 1 FROM calendar_slots WHERE recruiter_id=? AND start > ? LIMIT 1",
                    (recruiter_id, now().isoformat())).fetchone():
        return
    day = (now().astimezone(TUNIS) + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    n = 0
    while n < days:
        if day.weekday() < 5:  # Mon-Fri
            for i, hour in enumerate((9, 10, 11, 14, 15)):
                start = day.replace(hour=hour)
                # deterministic "busy" pattern so the recruiter isn't free all day
                status = "busy" if (day.day + i) % 3 == 0 else "free"
                conn.execute("INSERT INTO calendar_slots VALUES (?,?,?,?,?,NULL)",
                             (f"SLOT-{recruiter_id}-{start:%Y%m%d%H%M}", recruiter_id, start.isoformat(),
                              (start + timedelta(minutes=SLOT_MIN)).isoformat(), status))
            n += 1
        day += timedelta(days=1)


def is_known_recruiter(recruiter_id: str, conn: sqlite3.Connection | None = None) -> bool:
    """The default demo calendar, or a real recruiter / HR manager account. Stops callers creating a calendar
    (50 rows each) for any made-up id."""
    if recruiter_id == "recruiter":
        return True
    own = conn is None
    conn = conn or connect()
    try:
        return conn.execute("SELECT 1 FROM auth_users WHERE id = ? AND role IN ('recruiter','hr_manager') "
                            "AND active = 1", (recruiter_id,)).fetchone() is not None
    finally:
        if own:
            conn.close()


def free_slots(recruiter_id: str, n: int = 3, conn: sqlite3.Connection | None = None) -> list[dict]:
    own = conn is None
    conn = conn or connect()
    try:
        _ensure_slots(conn, recruiter_id)
        rows = conn.execute(
            "SELECT id, start, end FROM calendar_slots WHERE recruiter_id=? AND status='free' AND start > ? "
            "ORDER BY start LIMIT ?", (recruiter_id, now().isoformat(), n)).fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


def book(conn: sqlite3.Connection, slot_id: str, candidate_id: str) -> dict:
    """Only called by the executor, after approval."""
    r = conn.execute("SELECT * FROM calendar_slots WHERE id = ?", (slot_id,)).fetchone()
    if not r:
        raise HTTPException(404, "slot not found")
    if r["status"] != "free":
        raise HTTPException(409, "slot is no longer free")
    conn.execute("UPDATE calendar_slots SET status='booked', candidate_id=? WHERE id=?", (candidate_id, slot_id))
    return {"id": slot_id, "start": r["start"], "end": r["end"]}


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)
