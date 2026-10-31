"""Interview loop closer (built, not demoed): 2-minute structured scorecard + manager reminders.

Scorecards are typed only (ratings 1-4 per fixed criterion + recommendation enum): no free text to escape or leak.
"""
import sqlite3
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, conint

from ..contracts import Role, UserOut
from ..db import connect, register_schema, tx
from . import audit
from .common import canonical_json, new_id, now_iso


Rating = conint(ge=1, le=4)


class Ratings(BaseModel, extra="forbid"):
    technical: Rating
    problem_solving: Rating
    communication: Rating
    team_fit: Rating


class Scorecard(BaseModel, extra="forbid"):
    ratings: Ratings
    recommendation: Literal["strong_no", "no", "yes", "strong_yes"]


@register_schema
def _schema(conn: sqlite3.Connection):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS interviews (
            id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL,
            job_id TEXT NOT NULL,
            slot_id TEXT NOT NULL,
            interviewer_id TEXT NOT NULL,
            scheduled_start TEXT NOT NULL,
            scheduled_end TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'scheduled'
        );
        CREATE TABLE IF NOT EXISTS interview_scorecards (
            interview_id TEXT PRIMARY KEY REFERENCES interviews(id),
            interviewer_id TEXT NOT NULL,
            ratings TEXT NOT NULL,
            recommendation TEXT NOT NULL,
            submitted_at TEXT NOT NULL
        );
        """
    )


def create_interview(conn: sqlite3.Connection, candidate_id: str, job_id: str, slot: dict, interviewer_id: str) -> str:
    iid = new_id("INT")
    conn.execute("INSERT INTO interviews VALUES (?,?,?,?,?,?,?, 'scheduled')",
                 (iid, candidate_id, job_id, slot["id"], interviewer_id, slot["start"], slot["end"]))
    return iid


def submit_scorecard(interview_id: str, card: Scorecard, user: UserOut) -> dict:
    with tx() as conn:
        r = conn.execute("SELECT * FROM interviews WHERE id = ?", (interview_id,)).fetchone()
        if not r:
            raise HTTPException(404, "interview not found")
        # object-level check: the assigned interviewer, or an HR manager
        if user.role != Role.hr_manager and r["interviewer_id"] != user.id:
            raise HTTPException(404, "interview not found")
        if conn.execute("SELECT 1 FROM interview_scorecards WHERE interview_id = ?", (interview_id,)).fetchone():
            raise HTTPException(409, "scorecard already submitted")
        ratings = card.ratings.model_dump()
        conn.execute("INSERT INTO interview_scorecards VALUES (?,?,?,?,?)",
                     (interview_id, user.id, canonical_json(ratings), card.recommendation, now_iso()))
        conn.execute("UPDATE interviews SET status = 'scored' WHERE id = ?", (interview_id,))
        audit.append(user.id, "interview.scorecard", "interview", interview_id,
                     {"ratings": ratings, "recommendation": card.recommendation}, conn=conn)
    return {"interview_id": interview_id, "ratings": ratings, "recommendation": card.recommendation}


def reminders() -> list[dict]:
    """Interviews that ended without a scorecard: the manager gets nudged."""
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT i.* FROM interviews i LEFT JOIN interview_scorecards s ON s.interview_id = i.id "
            "WHERE s.interview_id IS NULL AND i.scheduled_end < ? ORDER BY i.scheduled_end", (now_iso(),)).fetchall()
    finally:
        conn.close()
    return [{"interview_id": r["id"], "candidate_id": r["candidate_id"], "interviewer_id": r["interviewer_id"],
             "ended_at": r["scheduled_end"]} for r in rows]
