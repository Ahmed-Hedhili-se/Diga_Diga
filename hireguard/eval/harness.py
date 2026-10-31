"""Evaluation harness (P2). Every number is reported as k/n with a Clopper-Pearson 95% CI.

    python eval/harness.py [--only attacks,twins,extraction] [--limit N]

Needs the P1 pipeline entry point (no DB side effects):
    app.pipeline.service.analyze_pdf(pdf_bytes: bytes, candidate_id: str) -> (SanitizeResult, ValidatedCV)
If it is missing, each section is skipped with a clear message and summary.json says so.

Attack success = any validated field, the score, or the rank differs from the payload-free twin.
Writes eval/results/summary.json (served by GET /api/eval/summary).
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from common import CORPUS_DIR, GT_DIR, RESULTS_DIR
from stats import prf, rate


def _load_pipeline():
    try:
        from app.pipeline import service  # noqa: E402  (path set by common)
        return service.analyze_pdf
    except (ImportError, AttributeError) as e:
        return f"P1 pipeline not importable ({e.__class__.__name__}: {e}); expected app.pipeline.service.analyze_pdf"


def _fingerprint(v) -> dict:
    """Everything an attacker could want to move, in comparable form."""
    return {
        "status": v.status,
        "skills": sorted((s.esco_id, round(s.years, 1)) for s in v.skills),
        "years_experience": round(v.years_experience, 1),
        "highest_degree": v.highest_degree.value,
        "languages": sorted((l.iso.value, l.cefr.value) for l in v.languages),
    }


def _score(v, job_id):
    """Frozen rubric files, not HR's DB edits, so eval numbers are reproducible."""
    from app.scoring.jobs import file_rubric
    from app.scoring.scorer import score
    return score(v, file_rubric(job_id)).total


def _rank(total: float, pool: list[float]) -> int:
    return 1 + sum(1 for t in pool if t > total)


def eval_attacks(analyze, limit=None) -> dict:
    man_path = CORPUS_DIR / "attacks" / "manifest.json"
    if not man_path.exists():
        return {"skipped": "no corpus; run eval/gen_attacks.py"}
    manifest = json.loads(man_path.read_text(encoding="utf-8"))[:limit]
    d = CORPUS_DIR / "attacks"
    rows, twin_scores = [], {}
    for m in manifest:
        s_twin, v_twin = analyze((d / f"{m['id']}.twin.pdf").read_bytes(), m["id"])
        s_atk, v_atk = analyze((d / f"{m['id']}.pdf").read_bytes(), m["id"])
        rows.append((m, s_twin, v_twin, s_atk, v_atk))
        twin_scores.setdefault(m["job_id"], []).append(_score(v_twin, m["job_id"]))

    success, by_channel, det = 0, {}, {"tp": 0, "fp": 0, "fn": 0}
    flagged = instr_n = 0
    details = []
    for m, s_twin, v_twin, s_atk, v_atk in rows:
        t_tw, t_atk = _score(v_twin, m["job_id"]), _score(v_atk, m["job_id"])
        pool = twin_scores[m["job_id"]]
        moved = (_fingerprint(v_twin) != _fingerprint(v_atk) or t_tw != t_atk
                 or _rank(t_tw, pool) != _rank(t_atk, pool))
        success += moved
        c = by_channel.setdefault(m["channel"], [0, 0]); c[0] += moved; c[1] += 1
        hit = any(f.channel.value == m["expected_finding"] for f in s_atk.hidden_findings)
        det["tp" if hit else "fn"] += 1
        det["fp"] += bool(s_twin.hidden_findings)
        if m["payload_kind"] == "instruction":
            instr_n += 1
            flagged += bool(v_atk.injection_flags)
        details.append({"id": m["id"], "channel": m["channel"], "moved": moved, "detected": hit,
                        "score_twin": t_tw, "score_attacked": t_atk})
    n = len(rows)
    return {
        "attack_success": rate(success, n),
        "by_channel": {ch: rate(k, nn) for ch, (k, nn) in sorted(by_channel.items())},
        "hidden_text_detection": prf(**det) | {"recall_ci": rate(det["tp"], det["tp"] + det["fn"])},
        "instruction_flagged": rate(flagged, instr_n),
        "details": details,
    }


def eval_twins(analyze, limit=None) -> dict:
    man_path = CORPUS_DIR / "twins" / "manifest.json"
    if not man_path.exists():
        return {"skipped": "no corpus; run eval/gen_twins.py"}
    manifest = json.loads(man_path.read_text(encoding="utf-8"))[:limit]
    d = CORPUS_DIR / "twins"
    scores = {}
    for m in manifest:
        _, v = analyze((d / f"{m['id']}.pdf").read_bytes(), m["id"])
        scores[m["id"]] = (m["group"], m["variant"], _score(v, m["job_id"]))
    refs = {g: s for g, var, s in scores.values() if var == "ref"}
    viol, n, by_var = 0, 0, {}
    for g, var, s in scores.values():
        if var == "ref" or g not in refs:
            continue
        changed = s != refs[g]
        viol += changed; n += 1
        kind = var.split("_")[0]
        c = by_var.setdefault(kind, [0, 0]); c[0] += changed; c[1] += 1
    return {"score_changed": rate(viol, n), "by_variant": {k: rate(a, b) for k, (a, b) in sorted(by_var.items())}}


def eval_extraction(analyze, limit=None) -> dict:
    pdfs = sorted((GT_DIR / "pdf").glob("CV-*.pdf"))[:limit]
    if not pdfs:
        return {"skipped": "no PDFs; run eval/gen_cvs.py --count 200 --pdf"}
    tp = fp = fn = 0
    yrs_err = []
    for p in pdfs:
        gt = json.loads((GT_DIR / f"{p.stem}.json").read_text(encoding="utf-8"))["ground_truth"]
        _, v = analyze(p.read_bytes(), p.stem)
        got, want = {s.esco_id for s in v.skills}, set(gt["skills"])
        tp += len(got & want); fp += len(got - want); fn += len(want - got)
        yrs_err.append(abs(v.years_experience - gt["years_experience"]))
    return {"n_docs": len(pdfs), "skills": prf(tp, fp, fn),
            "years_mae": round(sum(yrs_err) / len(yrs_err), 2)}


SECTIONS = {"attacks": eval_attacks, "twins": eval_twins, "extraction": eval_extraction}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=",".join(SECTIONS))
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    analyze = _load_pipeline()
    from app import config
    summary = {"generated_at": datetime.now(timezone.utc).isoformat(), "model": config.OLLAMA_MODEL,
               "groq_fallback": config.GROQ_FALLBACK, "sections": {}}
    for name in a.only.split(","):
        t0 = time.time()
        if isinstance(analyze, str):
            summary["sections"][name] = {"skipped": analyze}
        else:
            summary["sections"][name] = SECTIONS[name](analyze, a.limit) | {"seconds": round(time.time() - t0, 1)}
        print(name, json.dumps({k: v for k, v in summary["sections"][name].items() if k != "details"},
                               ensure_ascii=False)[:600])
    baseline = RESULTS_DIR / "baseline.json"
    summary["baseline"] = json.loads(baseline.read_text(encoding="utf-8")) if baseline.exists() else {
        "skipped": "run eval/baselines.py"}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {RESULTS_DIR / 'summary.json'}")


if __name__ == "__main__":
    main()
