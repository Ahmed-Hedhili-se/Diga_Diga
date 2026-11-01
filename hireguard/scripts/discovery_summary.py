#!/usr/bin/env python3
"""What the customer calls let us say.

    python scripts/discovery_summary.py [--file docs/discovery/call_log.csv]

Reads the call log and prints the number of calls, how many asked for a pilot, the median of every numeric column (blanks ignored, with
the number of people who answered), and the sentences the pitch may quote. It never prints a figure the log does not support: with no
rows it says so, and with fewer than three calls it tells you to quote people, not percentages. Standard library only.
"""
from __future__ import annotations

import argparse
import csv
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs" / "discovery" / "call_log.csv"
NUMERIC = ["size_staff", "hires_per_year", "cvs_per_role", "minutes_per_cv", "days_seat_empty"]
LABELS = {"size_staff": "staff", "hires_per_year": "hires per year", "cvs_per_role": "CVs per role",
          "minutes_per_cv": "minutes to read a CV", "days_seat_empty": "days a seat stays empty"}


def number(cell: str | None) -> float | None:
    try:
        return float((cell or "").strip().replace(",", ".")) if (cell or "").strip() else None
    except ValueError:
        return None


def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return [r for r in csv.DictReader(f) if any((v or "").strip() for v in r.values())]


def summarise(rows: list[dict[str, str]]) -> dict:
    pilot = [(r.get("would_pilot") or "").strip().lower() for r in rows]
    medians = {}
    for col in NUMERIC:
        vals = [v for v in (number(r.get(col)) for r in rows) if v is not None]
        if vals:
            medians[col] = (statistics.median(vals), len(vals))
    return {"n": len(rows), "yes": pilot.count("yes"), "maybe": pilot.count("maybe"), "no": pilot.count("no"),
            "medians": medians, "quotes": [(r.get("company") or "?", r["best_quote"].strip()) for r in rows
                                           if (r.get("best_quote") or "").strip()]}


def fmt(x: float) -> str:
    return f"{x:g}"


def report(s: dict) -> list[str]:
    n = s["n"]
    if n == 0:
        return ["n calls: 0", "n = 0: no claim possible"]
    out = [f"n calls: {n}", f"would_pilot=yes: {s['yes']}  (maybe: {s['maybe']}, no: {s['no']})"]
    for col, (med, k) in s["medians"].items():
        out.append(f"median {LABELS[col]}: {fmt(med)}  (n = {k} answered)")
    out += ["", "The pitch may quote:", f"  We spoke to n={n} people; {s['yes']} asked for a pilot."]
    for col, (med, k) in s["medians"].items():
        out.append(f"  Median {LABELS[col]}: {fmt(med)} (n = {k}).")
    if n < 3:
        out.append("  With fewer than 3 calls, show the quotes below instead of any percentage.")
    if s["quotes"]:
        out += ["", "Quotes (exact words):"] + [f"  [{company}] {quote}" for company, quote in s["quotes"]]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--file", type=Path, default=DEFAULT)
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    if not a.file.exists():
        print(f"no call log at {a.file}")
        return 1
    print("\n".join(report(summarise(read(a.file)))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
