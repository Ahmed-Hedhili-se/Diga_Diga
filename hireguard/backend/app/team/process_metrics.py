"""HR process metrics (HR Nexus, U4): how long each hiring step takes, measured from the audit log.

This measures the work, not the people: stages are timed per candidate file and only reported per stage
(count, median, p95). No reviewer, recruiter or employee appears in the output.

Stages, read from the hash-chained audit log:
  received      pipeline.process_cv
  shortlisted   executor.run of a shortlist_commit item (every candidate in it)
  invited       executor.run of an interview_booking item
  interviewed   interview.scorecard (the interview's candidate)
  offer_sent    executor.run of an offer item
  closed        executor.run of a status_change to rejected / withdrawn / hired

Little's law (L = λW, Little 1961) links arrivals per day λ, mean days in the pipeline W and files in
progress L. Expected and observed L disagree when the window is not in steady state, which is worth
saying out loud rather than hiding.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from statistics import mean

from ..db import connect

STAGES = ["received", "shortlisted", "invited", "interviewed", "offer_sent"]
CLOSING = {"rejected", "withdrawn", "hired"}
MIN_N = 3  # a transition needs this many files before it can be called the bottleneck


def events_from_db(conn: sqlite3.Connection | None = None) -> list[tuple[str, str, str]]:
    own = conn is None
    conn = conn or connect()
    try:
        out: list[tuple[str, str, str]] = []
        rows = conn.execute("SELECT action, object_id, ts, details FROM audit_log WHERE action IN "
                            "('pipeline.process_cv', 'executor.run', 'interview.scorecard') ORDER BY seq").fetchall()
        for r in rows:
            if r["action"] == "pipeline.process_cv":
                out.append((r["object_id"], "received", r["ts"]))
            elif r["action"] == "interview.scorecard":
                i = conn.execute("SELECT candidate_id FROM interviews WHERE id = ?", (r["object_id"],)).fetchone()
                if i:
                    out.append((i["candidate_id"], "interviewed", r["ts"]))
            else:
                kind = json.loads(r["details"]).get("kind")
                item = conn.execute("SELECT payload FROM approval_items WHERE id = ?", (r["object_id"],)).fetchone()
                p = json.loads(item["payload"]) if item else {}
                if kind == "shortlist_commit":
                    out += [(c, "shortlisted", r["ts"]) for c in p.get("candidate_ids", [])]
                elif kind == "interview_booking" and p.get("candidate_id"):
                    out.append((p["candidate_id"], "invited", r["ts"]))
                elif kind == "offer" and p.get("candidate_id"):
                    out.append((p["candidate_id"], "offer_sent", r["ts"]))
                elif kind == "status_change" and p.get("status_to") in CLOSING and p.get("object_type") == "candidate":
                    out.append((p["object_id"], "closed", r["ts"]))
        return out
    finally:
        if own:
            conn.close()


def _q(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    pos = (len(xs) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def _days(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds() / 86400


def _summary(xs: list[float]) -> dict:
    if not xs:
        return {"n": 0, "median_days": None, "p95_days": None}
    return {"n": len(xs), "median_days": round(_q(xs, 0.5), 1), "p95_days": round(_q(xs, 0.95), 1)}


def metrics(events: list[tuple[str, str, str]], now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    files: dict[str, dict[str, datetime]] = {}
    for cid, stage, ts in events:
        t = datetime.fromisoformat(ts)
        cur = files.setdefault(cid, {})
        if stage not in cur or t < cur[stage]:
            cur[stage] = t
    files = {c: f for c, f in files.items() if "received" in f}

    transitions = []
    for a, b in zip(STAGES, STAGES[1:]):
        d = [_days(f[a], f[b]) for f in files.values() if a in f and b in f and f[b] >= f[a]]
        transitions.append({"from": a, "to": b, **_summary(d)})
    ranked = [t for t in transitions if t["n"] >= MIN_N]
    bottleneck = max(ranked, key=lambda t: t["median_days"]) if ranked else None

    done = [_days(f["received"], f["offer_sent"]) for f in files.values() if "offer_sent" in f]
    open_files = [f for f in files.values() if "offer_sent" not in f and "closed" not in f]
    wip = {s: 0 for s in STAGES[:-1]}
    for f in open_files:
        wip[max((s for s in STAGES if s in f), key=STAGES.index)] += 1

    arrivals = [f["received"] for f in files.values()]
    window = max(1.0, _days(min(arrivals), now)) if arrivals else None
    lam = len(arrivals) / window if window else None
    sojourn = [_days(f["received"], f.get("offer_sent") or f.get("closed") or now) for f in files.values()]
    w = mean(sojourn) if sojourn else None
    return {
        "files": len(files),
        "reached": {s: sum(1 for f in files.values() if s in f) for s in STAGES},
        "closed": sum(1 for f in files.values() if "closed" in f),
        "transitions": transitions,
        "bottleneck": bottleneck,
        "time_to_offer": _summary(done),
        "wip": wip,
        "littles_law": None if lam is None else {
            "window_days": round(window, 1), "arrivals_per_day": round(lam, 2), "mean_days_in_pipeline": round(w, 1),
            "expected_in_progress": round(lam * w, 1), "observed_in_progress": len(open_files)},
    }
