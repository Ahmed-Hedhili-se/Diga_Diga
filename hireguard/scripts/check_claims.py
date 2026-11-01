#!/usr/bin/env python3
"""Every percentage we publish must have a source.

    python scripts/check_claims.py            # exit 1 if any percentage is unsourced
    python scripts/check_claims.py --warn     # same report, always exit 0

Scans docs/pitch.md, docs/business.md, brand/README.md and the two sales sheets. A percentage is accepted when:
  - the same number appears as a percentage in docs/evidence.md, or
  - it comes from eval/results/*.json (a `rate`, a k/n pair, a 95% interval bound, or a percentage inside a result text), or
  - it is the "95%" of "95% CI", or
  - its line says it is an assumption, a hypothesis, an estimate or our calculation (printed as LABELLED).
Anything else is UNSOURCED. Standard library only; no network.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [ROOT / "docs" / "pitch.md", ROOT / "docs" / "business.md", ROOT / "brand" / "README.md",
           ROOT / "brand" / "sales" / "one-pager.html", ROOT / "brand" / "sales" / "security-sheet.html"]
EVIDENCE = ROOT / "docs" / "evidence.md"
RESULTS = ROOT / "eval" / "results"

PCT = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s?%")
CI = re.compile(r"\s?(?:CI\b|confidence)", re.I)
LABEL = re.compile(r"assumption|hypothes|estimate|my calculation|our calculation", re.I)


def canon(x: float) -> str:
    return f"{x:.1f}".rstrip("0").rstrip(".")


def numbers_in(text: str) -> set[str]:
    return {canon(float(m.group(1))) for m in PCT.finditer(text)}


def _add_fraction(out: set[str], frac: float) -> None:
    out.add(canon(round(frac * 100, 1)))
    out.add(canon(round(frac * 100)))


def _walk(node, out: set[str]) -> None:
    if isinstance(node, dict):
        if isinstance(node.get("rate"), (int, float)):
            _add_fraction(out, node["rate"])
        k, n = node.get("k"), node.get("n")
        if isinstance(k, int) and isinstance(n, int) and n:
            _add_fraction(out, k / n)
        ci = node.get("ci95")
        if isinstance(ci, list):
            for v in ci:
                if isinstance(v, (int, float)):
                    _add_fraction(out, v)
        for v in node.values():
            _walk(v, out)
    elif isinstance(node, list):
        for v in node:
            _walk(v, out)
    elif isinstance(node, str):
        out |= numbers_in(node)


def result_numbers(results_dir: Path) -> set[str]:
    out: set[str] = set()
    for p in sorted(results_dir.glob("*.json")) if results_dir.is_dir() else []:
        try:
            _walk(json.loads(p.read_text(encoding="utf-8")), out)
        except (OSError, ValueError):
            continue
    return out


def check(targets: list[Path], evidence: Path, results_dir: Path) -> list[tuple[Path, int, str, str, str]]:
    ev = numbers_in(evidence.read_text(encoding="utf-8")) if evidence.exists() else set()
    res = result_numbers(results_dir)
    rows = []
    for path in targets:
        if not path.exists():
            continue
        for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for m in PCT.finditer(line):
                num, token = canon(float(m.group(1))), m.group(0)
                if num == "95" and CI.match(line, m.end()):
                    status = "OK"
                elif num in ev:
                    status = "OK"
                elif num in res:
                    status = "OK"
                elif LABEL.search(line):
                    status = "LABELLED"
                else:
                    status = "UNSOURCED"
                rows.append((path, no, token, status, line.strip()[:110]))
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--warn", action="store_true", help="report only; always exit 0")
    ap.add_argument("--files", nargs="*", type=Path, help="files to scan instead of the default list")
    ap.add_argument("--evidence", type=Path, default=EVIDENCE)
    ap.add_argument("--results", type=Path, default=RESULTS)
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):  # a Windows console may not encode every character in a quoted line
        sys.stdout.reconfigure(errors="replace")
    rows = check(a.files if a.files else TARGETS, a.evidence, a.results)
    for path, no, token, status, line in rows:
        try:
            shown = path.relative_to(ROOT)
        except ValueError:
            shown = path
        print(f"{status:<9} {shown}:{no}: {token}   {line}")
    bad = sum(r[3] == "UNSOURCED" for r in rows)
    print(f"\n{len(rows)} percentage(s): {sum(r[3] == 'OK' for r in rows)} sourced, "
          f"{sum(r[3] == 'LABELLED' for r in rows)} labelled, {bad} unsourced")
    return 0 if (a.warn or not bad) else 1


if __name__ == "__main__":
    sys.exit(main())
