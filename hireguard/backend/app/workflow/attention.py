"""Reviewer attention guard (P3). Human-in-the-loop only works while the human is still looking.

Canaries (planted defects, see approvals.py) are the measurement. Every decision records the size of
the batch it was made in, so we can see whether canaries are missed more often in big batches
(automation bias, EU AI Act Art. 14(4)(b)). The guard reacts to recent misses by shrinking the
maximum routine batch size; at two misses in the recent window, routine items are reviewed one by one.

Metrics are aggregated over the process (batch sizes), not used to rank reviewers.
"""
from __future__ import annotations

import os
import sqlite3

from scipy.stats import beta

from ..db import connect, register_schema

DEFAULT_MAX_BATCH = int(os.getenv("HG_MAX_BATCH", "10"))
RECENT_CANARIES = 10
# misses among the last RECENT_CANARIES canaries -> max routine batch size
CAP_BY_MISSES = {0: DEFAULT_MAX_BATCH, 1: max(1, DEFAULT_MAX_BATCH // 2)}
BUCKETS = [(1, 1, "1 (one by one)"), (2, 5, "2-5"), (6, 10, "6-10"), (11, 10_000, "11+")]


@register_schema
def _schema(conn: sqlite3.Connection):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS approval_review_context (
            item_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            batch_size INTEGER NOT NULL,
            at TEXT NOT NULL
        );
        """
    )


def record(conn: sqlite3.Connection, item_id: str, user_id: str, batch_size: int, at: str):
    conn.execute("INSERT INTO approval_review_context VALUES (?,?,?,?)", (item_id, user_id, batch_size, at))


def _recent(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT outcome FROM approval_canary_results ORDER BY at DESC LIMIT ?",
                        (RECENT_CANARIES,)).fetchall()
    return [r["outcome"] for r in rows]


def max_batch_size(conn: sqlite3.Connection | None = None) -> int:
    own = conn is None
    conn = conn or connect()
    try:
        misses = _recent(conn).count("miss")
    finally:
        if own:
            conn.close()
    return CAP_BY_MISSES.get(misses, 1)


def _ci(k: int, n: int) -> list[float] | None:
    if n == 0:
        return None
    lo = 0.0 if k == 0 else float(beta.ppf(0.025, k, n - k + 1))
    hi = 1.0 if k == n else float(beta.ppf(0.975, k + 1, n - k))
    return [round(lo, 3), round(hi, 3)]


def stats() -> dict:
    conn = connect()
    try:
        rows = conn.execute(
            """SELECT c.outcome, x.batch_size FROM approval_canary_results c
               JOIN approval_review_context x ON x.item_id = c.item_id AND x.user_id = c.user_id"""
        ).fetchall()
        recent = _recent(conn)
        cap = max_batch_size(conn)
    finally:
        conn.close()
    by_bucket = []
    for lo, hi, label in BUCKETS:
        outs = [r["outcome"] for r in rows if lo <= r["batch_size"] <= hi]
        k, n = outs.count("miss"), len(outs)
        by_bucket.append({"batch_size": label, "canaries": n, "missed": k,
                          "miss_rate": round(k / n, 3) if n else None, "ci95": _ci(k, n)})
    return {
        "max_batch_size": cap,
        "default_max_batch_size": DEFAULT_MAX_BATCH,
        "recent": {"canaries": len(recent), "missed": recent.count("miss")},
        "by_batch_size": by_bucket,
        "rule": f"misses in the last {RECENT_CANARIES} canaries: 0 -> {CAP_BY_MISSES[0]}, "
                f"1 -> {CAP_BY_MISSES[1]}, 2+ -> 1 (one by one)",
    }
