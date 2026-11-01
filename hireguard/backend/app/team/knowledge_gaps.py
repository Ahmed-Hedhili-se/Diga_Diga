"""Knowledge-gap radar (HR Nexus, U5): which handbook sections fail employees, without storing questions.

The Answer Desk calls record(section, lang) once per question: the handbook section it answered from, or
None when nothing matched and the question went to HR. The question text, the employee and the answer
are never stored here. radar() counts per section and per ISO week and hides every count below K
(k-anonymity, Sweeney 2002), so a rare question cannot point at one person.
"""
from __future__ import annotations

import json
import random
import sqlite3
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache

from ..config import DATA_DIR
from ..db import connect, register_schema, tx

K = 5
LANGS = ("fr", "en", "ar")


@register_schema
def _schema(conn: sqlite3.Connection):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS answer_desk_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week TEXT NOT NULL,               -- ISO week, e.g. 2026-W44
            section TEXT,                     -- NULL = no match, forwarded to HR
            lang TEXT NOT NULL
        );
        """
    )


@lru_cache(maxsize=1)
def sections() -> list[str]:
    return list(json.loads((DATA_DIR / "handbook" / "sections.json").read_text(encoding="utf-8")))


def _week(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def record(section: str | None, lang: str, when: date | None = None, conn: sqlite3.Connection | None = None):
    if section is not None and section not in sections():
        raise ValueError("unknown handbook section")
    when = when or datetime.now(timezone.utc).date()
    lang = lang if lang in LANGS else "other"
    if conn is None:
        with tx() as c:
            return record(section, lang, when, conn=c)
    conn.execute("INSERT INTO answer_desk_log (week, section, lang) VALUES (?,?,?)", (_week(when), section, lang))


def _cell(n: int, k: int) -> int | None:
    return n if n >= k or n == 0 else None


def radar(k: int = K, weeks: int = 8, today: date | None = None) -> dict:
    today = today or datetime.now(timezone.utc).date()
    since = _week(today - timedelta(weeks=weeks - 1))
    conn = connect()
    try:
        rows = conn.execute("SELECT week, section FROM answer_desk_log WHERE week >= ?", (since,)).fetchall()
    finally:
        conn.close()
    total = len(rows)
    by_section: dict[str | None, int] = {}
    by_week: dict[str, list[int]] = {}
    for r in rows:
        by_section[r["section"]] = by_section.get(r["section"], 0) + 1
        w = by_week.setdefault(r["week"], [0, 0])
        w[0] += 1
        w[1] += r["section"] is None
    no_match = by_section.pop(None, 0)
    return {
        "k": k, "since_week": since, "questions": _cell(total, k),
        "no_match": {"count": _cell(no_match, k),
                     "share": round(no_match / total, 3) if total >= k and no_match >= k else None},
        "sections": sorted(({"section": s, "count": _cell(by_section.get(s, 0), k),
                             "suppressed": 0 < by_section.get(s, 0) < k} for s in sections()),
                           key=lambda x: -(x["count"] or 0)),
        "weeks": [{"week": w, "questions": _cell(n, k), "no_match": _cell(m, k),
                   "no_match_share": round(m / n, 3) if n >= k and m >= k else None}
                  for w, (n, m) in sorted(by_week.items())],
    }

# ---------------------------------------------------------------- demo seed (fictional)


SEED_WEIGHTS = {  # relative question volume per section over six weeks; None = nothing matched
    "6. Remote work": 9, "2. Annual leave": 8, "5. Maternity, paternity and family leave": 5,
    "9. HR documents and certificates": 5, "7. Expenses and travel": 4, "4. Sick leave": 3,
    "8. Training and development": 2, "1. Working hours": 2, "3. Public holidays": 1, None: 6,
}


def seed_log(n: int = 140, seed: int = 11):
    rng = random.Random(seed)
    keys, weights = list(SEED_WEIGHTS), list(SEED_WEIGHTS.values())
    today = datetime.now(timezone.utc).date()
    with tx() as conn:
        if conn.execute("SELECT COUNT(*) FROM answer_desk_log").fetchone()[0]:
            return
        for _ in range(n):
            record(rng.choices(keys, weights)[0], rng.choice(LANGS), today - timedelta(days=rng.randrange(42)),
                   conn=conn)
