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


# ---------------------------------------------------------------- ROI calculator (what would it be worth to you?)
#
# Pure and deterministic: no model, no database. Every input has a default that is an ASSUMPTION; a value the user typed is
# marked "entered". Sources are ids in docs/evidence.md; None means "our hypothesis, to be checked in customer calls".

ROI_INPUTS = {
    # name: (default, low, high, source_id)
    "roles_per_year": (20, 1, 1000, None),
    "cvs_per_role": (150, 1, 5000, None),
    "minutes_per_cv": (4.0, 0.5, 60.0, None),
    "recruiter_cost_tnd_per_hour": (14.2, 1.0, 500.0, "E10"),  # 2,500 TND gross a month / 176 h; E10 has under 20 respondents
    "days_saved_per_role": (5.0, 0.0, 60.0, None),
    "vacancy_cost_tnd_per_day": (180.0, 0.0, 10000.0, None),   # a demo value, not a measurement
    "plan_price_tnd_per_month": (400.0, 0.0, 20000.0, None),   # pricing hypothesis, see docs/business.md
}


def roi(entered: dict[str, float] | None = None) -> dict:
    """Value of the product for one customer profile. `entered` holds only what the user typed; the rest is an assumption.

    payback_months is how many months of the value created are needed to cover one year of the plan price.
    """
    entered = entered or {}
    values, inputs = {}, {}
    for name, (default, low, high, source) in ROI_INPUTS.items():
        if name in entered:
            v = entered[name]
            if not low <= v <= high:
                raise ValueError(f"{name} must be between {low:g} and {high:g}")
        else:
            v = default
        values[name] = v
        inputs[name] = {"value": v, "status": "entered" if name in entered else "assumption", "source_id": source}
    cvs = values["roles_per_year"] * values["cvs_per_role"]
    screening = cvs * values["minutes_per_cv"] / 60 * values["recruiter_cost_tnd_per_hour"]
    faster = values["roles_per_year"] * values["days_saved_per_role"] * values["vacancy_cost_tnd_per_day"]
    total = screening + faster
    price_year = values["plan_price_tnd_per_month"] * 12
    ratio = lambda x: round(x / price_year, 1) if price_year > 0 else None
    return {
        "inputs": inputs,
        "outputs": {
            "cvs_per_year": cvs,
            "screening_hours_per_year": round(cvs * values["minutes_per_cv"] / 60, 1),
            "screening_value_tnd": round(screening),
            "faster_hiring_value_tnd": round(faster),
            "total_value_tnd": round(total),
            "plan_price_tnd_per_year": round(price_year),
            "total_value_over_price": ratio(total),
            "screening_only_over_price": ratio(screening),
            "payback_months": round(price_year / (total / 12), 1) if total > 0 else None,
        },
        "note": "Hypothesis: replace the assumptions with your own numbers. Nothing here is a measured result.",
    }
