"""Load test for "reliable on real volumes": N fictional CVs through the real pipeline and database.

    python eval/load_test.py [--n 300] [--extraction oracle|llm]

Runs app.pipeline.service.process_cv (sanitize, detect, extract, validate, score, persist, audit) on a
temporary database, one CV after another, and reports throughput, p50/p95 latency per CV and errors.
Inputs: the 200 ground-truth CV PDFs, then the 40 attack and the twin PDFs from eval/corpus, cycled to N.
  oracle  ground-truth extraction: the code path and the database only, no model
  llm     Qwen3 via Ollama: the real thing, on a GPU laptop (refuses to run if the model is down)
Writes eval/results/load_test.json. Fictional data only.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from common import CORPUS_DIR, GT_DIR, RESULTS_DIR


def inputs() -> list[tuple[bytes, dict]]:
    out = []
    for p in sorted((GT_DIR / "pdf").glob("CV-*.pdf")):
        out.append((p.read_bytes(), json.loads((GT_DIR / f"{p.stem}.json").read_text(encoding="utf-8"))["ground_truth"]))
    for sub in ("attacks", "twins"):
        man = CORPUS_DIR / sub / "manifest.json"
        if man.exists():
            for m in json.loads(man.read_text(encoding="utf-8")):
                pdf = CORPUS_DIR / sub / f"{m['id']}.pdf"
                if pdf.exists():
                    out.append((pdf.read_bytes(), m["ground_truth"]))
    return out


def _q(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--extraction", choices=["oracle", "llm"], default="oracle")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="hg-load-"))
    os.environ.update({"HG_DB_PATH": str(tmp / "load.db"), "HG_UPLOAD_DIR": str(tmp / "uploads"),
                       "HG_ANCHOR_LOOP": "0"})
    import app.main  # noqa: F401,E402  registers every schema (path set by common)
    from app.db import init_db
    from app.pipeline.demo import _ollama_ready
    from app.pipeline.sanitizer import sanitize
    from app.pipeline.service import process_cv
    from oracle import gt_extraction

    if args.extraction == "llm" and not _ollama_ready():
        raise SystemExit("llm mode needs Ollama with the configured model; nothing was measured")
    init_db()
    data = inputs()
    if not data:
        raise SystemExit("no input PDFs: run eval/gen_cvs.py, gen_attacks.py and gen_twins.py first")

    lat, errors, status = [], {}, {}
    t0 = time.perf_counter()
    for i in range(args.n):
        pdf, gt = data[i % len(data)]
        override = gt_extraction(gt, sanitize(pdf).visible_text) if args.extraction == "oracle" else None
        s = time.perf_counter()
        try:
            res = process_cv(pdf, gt["name"], gt["email"], gt["job_id"], candidate_id=f"CAND-LT{i:04d}",
                             actor="system:load_test", extraction_override=override)
            status[res["status"]] = status.get(res["status"], 0) + 1
        except Exception as e:  # noqa: BLE001  every failure is counted by type, none is hidden
            errors[type(e).__name__] = errors.get(type(e).__name__, 0) + 1
        lat.append(time.perf_counter() - s)
    wall = time.perf_counter() - t0

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(), "extraction": args.extraction,
        "scope": "code path and database only; the model is not exercised" if args.extraction == "oracle"
                 else "full pipeline including the model",
        "n": args.n, "distinct_inputs": len(data), "errors": errors, "status": status,
        "pipeline_seconds_total": round(sum(lat), 1),
        "cvs_per_minute": round(60 * args.n / sum(lat), 1),
        "latency_ms": {"p50": round(1000 * _q(lat, 0.5)), "p95": round(1000 * _q(lat, 0.95)),
                       "max": round(1000 * max(lat))},
        "wall_seconds_including_oracle_prep": round(wall, 1),
        "db_mb": round((tmp / "load.db").stat().st_size / 1e6, 1),
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "load_test.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
