"""Demo job offers and HR-written rubrics (P2).

Rubric defaults live in data/rubrics/<job_id>.json; an HR edit (PUT /jobs/{id}/rubric)
is stored in score_rubrics and wins over the file.
"""
from __future__ import annotations

import sqlite3
from datetime import date

from ..config import DATA_DIR
from ..contracts import Rubric
from ..db import connect, register_schema

RUBRIC_DIR = DATA_DIR / "rubrics"

# open_since / target_days / daily cost are demo inputs (fictional), shown on the money dashboard.
JOBS: dict[str, dict] = {
    "JOB-DATA-01": {"title": "Data Engineer (Python, SQL, ETL), Tunis", "open_since": "2026-09-01",
                    "target_days": 45, "daily_vacancy_cost_tnd": 220.0},
    "JOB-FS-02": {"title": "Full-stack developer (React, Node, PostgreSQL)", "open_since": "2026-09-20",
                  "target_days": 40, "daily_vacancy_cost_tnd": 180.0},
    "JOB-HR-03": {"title": "HR assistant (payroll, Tunisian labour law, Excel)", "open_since": "2026-10-10",
                  "target_days": 30, "daily_vacancy_cost_tnd": 90.0},
}


@register_schema
def _schema(conn: sqlite3.Connection):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS score_rubrics (
            job_id TEXT PRIMARY KEY,
            rubric_json TEXT NOT NULL,
            updated_by TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )


def list_jobs(today: date | None = None) -> list[dict]:
    today = today or date.today()
    out = []
    for job_id, j in JOBS.items():
        days_open = (today - date.fromisoformat(j["open_since"])).days
        out.append({"job_id": job_id, **j, "days_open": max(0, days_open)})
    return out


def file_rubric(job_id: str) -> Rubric:
    path = RUBRIC_DIR / f"{job_id}.json"
    return Rubric.model_validate_json(path.read_text(encoding="utf-8"))


def get_rubric(job_id: str) -> Rubric:
    if job_id not in JOBS:
        raise KeyError(job_id)
    conn = connect()
    try:
        row = conn.execute("SELECT rubric_json FROM score_rubrics WHERE job_id = ?", (job_id,)).fetchone()
    finally:
        conn.close()
    if row:
        return Rubric.model_validate_json(row["rubric_json"])
    return file_rubric(job_id)


def put_rubric(rubric: Rubric, user_id: str) -> Rubric:
    if rubric.job_id not in JOBS:
        raise KeyError(rubric.job_id)
    conn = connect()
    try:
        conn.execute(
            """INSERT INTO score_rubrics (job_id, rubric_json, updated_by) VALUES (?,?,?)
               ON CONFLICT(job_id) DO UPDATE SET rubric_json = excluded.rubric_json,
               updated_by = excluded.updated_by, updated_at = datetime('now')""",
            (rubric.job_id, rubric.model_dump_json(), user_id),
        )
    finally:
        conn.close()
    return rubric


def seed_jobs():
    """Called by app.seed: validates every rubric file and resets HR overrides to the files."""
    conn = connect()
    try:
        for job_id in JOBS:
            file_rubric(job_id)  # fail loudly on a broken file
            conn.execute("DELETE FROM score_rubrics WHERE job_id = ?", (job_id,))
    finally:
        conn.close()
