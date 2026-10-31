"""Simulated hiring history for the HR process panel (HR Nexus, U4). FICTIONAL PARAMETERS.

    python eval/process_sim.py [--files 150] [--days 60] [--seed 5]

A fresh demo database has no history: everything in it happened a minute ago. This script generates a
60-day history from stated, made-up stage delays and conversion rates, runs it through the same code the
live panel uses (app.team.process_metrics.metrics) and writes eval/results/process_sim.json, which the
UI labels "simulation". It shows what the panel reports; it measures nothing about any real company.
Replace PARAMS with figures from the HR interviews when they exist.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from datetime import datetime, timedelta, timezone

from common import RESULTS_DIR

# stage -> (median days after the previous stage, share of files that get there). Made up, stated.
PARAMS = {
    "shortlisted": (6.0, 0.35),
    "invited": (3.0, 0.85),
    "interviewed": (5.0, 0.90),
    "offer_sent": (9.0, 0.45),
}
SPREAD = 0.6            # lognormal sigma of every delay
CLOSE_MEDIAN = 2.0      # days between a "no" and closing the file


def simulate(files: int, days: int, seed: int, now: datetime) -> list[tuple[str, str, str]]:
    rng = random.Random(seed)
    start = now - timedelta(days=days)
    events = []
    for i in range(files):
        cid = f"SIM-{i:04d}"
        t = start + timedelta(days=rng.uniform(0, days))
        events.append((cid, "received", t.isoformat()))
        for stage, (median, share) in PARAMS.items():
            if rng.random() >= share:
                t += timedelta(days=rng.lognormvariate(math.log(CLOSE_MEDIAN), SPREAD))
                if t <= now:
                    events.append((cid, "closed", t.isoformat()))
                break
            t += timedelta(days=rng.lognormvariate(math.log(median), SPREAD))
            if t > now:
                break  # still in progress
            events.append((cid, stage, t.isoformat()))
    return events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", type=int, default=150)
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--seed", type=int, default=5)
    args = ap.parse_args()

    from app.team.process_metrics import metrics  # noqa: E402  (path set by common)

    now = datetime.now(timezone.utc).replace(microsecond=0)
    out = {
        "source": "simulation",
        "label": "Simulated history with made-up parameters. Shows the panel; measures no real company.",
        "params": {"stages": {s: {"median_days": m, "share": p} for s, (m, p) in PARAMS.items()},
                   "spread_sigma": SPREAD, "files": args.files, "days": args.days, "seed": args.seed},
        "generated_at": now.isoformat(),
        **metrics(simulate(args.files, args.days, args.seed, now), now),
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "process_sim.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    b = out["bottleneck"]
    print(f"{out['files']} simulated files; time to offer median {out['time_to_offer']['median_days']} d "
          f"(n={out['time_to_offer']['n']}); bottleneck {b['from']} -> {b['to']} ({b['median_days']} d)" if b else
          "no bottleneck (too few files)")


if __name__ == "__main__":
    main()
