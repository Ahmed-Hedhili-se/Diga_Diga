"""Money dashboard backend (P2): cost of vacancy, days to fill, hours saved, ROI.

Other modules call `record_activity(kind)` when work is done for HR. Minutes per unit are
stated assumptions (shown on the dashboard), to be replaced by HR interview findings.
"""
from __future__ import annotations

import sqlite3
from datetime import date

from ..db import connect, register_schema
from .jobs import list_jobs

# Manual minutes per unit of work. ASSUMPTIONS, to be checked against HR interviews.
MINUTES_PER_UNIT = {"cv_screening": 6.0, "emails": 4.0, "documents": 10.0, "answers": 5.0}
DEFAULT_HOURLY_COST_TND = 25.0


@register_schema
def _schema(conn: sqlite3.Connection):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS score_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS score_activity (
            kind TEXT PRIMARY KEY CHECK (kind IN ('cv_screening','emails','documents','answers')),
            count INTEGER NOT NULL DEFAULT 0
        );
        """
    )


def record_activity(kind: str, n: int = 1):
    if kind not in MINUTES_PER_UNIT:
        raise ValueError(kind)
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO score_activity (kind, count) VALUES (?, ?) "
            "ON CONFLICT(kind) DO UPDATE SET count = count + excluded.count",
            (kind, n),
        )
    finally:
        conn.close()


def get_hourly_cost() -> float:
    conn = connect()
    try:
        row = conn.execute("SELECT value FROM score_settings WHERE key = 'hourly_cost_tnd'").fetchone()
    finally:
        conn.close()
    return float(row["value"]) if row else DEFAULT_HOURLY_COST_TND


def set_hourly_cost(value: float):
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO score_settings (key, value) VALUES ('hourly_cost_tnd', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(value),),
        )
    finally:
        conn.close()


def dashboard(today: date | None = None) -> dict:
    conn = connect()
    try:
        counts = {r["kind"]: r["count"] for r in conn.execute("SELECT kind, count FROM score_activity")}
    finally:
        conn.close()
    hours = {k: round(counts.get(k, 0) * m / 60, 1) for k, m in MINUTES_PER_UNIT.items()}
    hours["total"] = round(sum(hours.values()), 1)
    hourly = get_hourly_cost()
    roles = [
        {
            "job_id": j["job_id"],
            "title": j["title"],
            "days_open": j["days_open"],
            "target_days": j["target_days"],
            "over_target_days": max(0, j["days_open"] - j["target_days"]),
            "cost_of_vacancy_tnd": round(j["days_open"] * j["daily_vacancy_cost_tnd"], 0),
        }
        for j in list_jobs(today)
    ]
    return {
        "roles": roles,
        "units": {k: counts.get(k, 0) for k in MINUTES_PER_UNIT},
        "minutes_per_unit": MINUTES_PER_UNIT,
        "hours_saved": hours,
        "hourly_cost_tnd": hourly,
        "roi_tnd": round(hours["total"] * hourly, 0),
    }
