"""Evaluation harness (P2). Every number is reported as k/n with a Clopper-Pearson 95% CI.

    python eval/harness.py [--only hidden,attacks,twins,emails,extraction] [--limit N] [--extraction auto|llm|oracle]

Extraction modes (every section in summary.json records which one produced it):
  llm     the configured model (Qwen3 via Ollama, local or Modal). Refuses to start when the model is unreachable:
          a dead model fails the attacked CV and its twin identically and would report a fake 0/40.
  oracle  ground-truth extraction (eval/oracle.py) through the real sanitizer, detector, validator and scorer.
          Measures the code path only. It says nothing about whether the model obeys injections: never report
          an oracle number as model robustness.
  auto    llm when reachable, otherwise oracle.

Sections:
  hidden      sanitizer only (no LLM): is hidden text found on attacked docs, and never on clean ones?
  attacks     40 attacked CVs vs their payload-free twins: did any field, the score or the rank move?
  twins       counterfactual twins (town, school, gap, CV language, ingénieur/ingénieure): did the score move?
  emails      100 emails (15 spoofed) through P3's email gate rules: right lane? spoofs contained?
  extraction  200 generated CVs vs ground truth: skill precision/recall/F1, years error

LLM cache: P1's extractor runs at temperature 0 with a fixed seed, so a byte-identical visible text gives
the same model input. Extractions are cached by sha256(model, visible text) in eval/results/raw/llm_cache.json.
When an attacked CV and its twin have the same visible text, the model is called once: this also keeps GPU
non-determinism from being counted as an attack success. Failed calls are never cached.

Each section is merged into eval/results/summary.json as soon as it finishes (served by GET /api/eval/summary).
"""
from __future__ import annotations

import argparse
import email
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from email import policy
from email.utils import parseaddr

import httpx

from common import CORPUS_DIR, GT_DIR, RESULTS_DIR, ROOT
from stats import prf, rate

SUMMARY = RESULTS_DIR / "summary.json"
CACHE_PATH = RESULTS_DIR / "raw" / "llm_cache.json"
EMAIL_DIR = ROOT / "data" / "emails"
UNDECODABLE = re.compile(r"^\[\d+ undecodable glyph")
EVAL_TIMEOUT = httpx.Timeout(300.0, connect=5.0)
ORACLE_SCOPE = ("oracle extraction (no LLM): measures sanitizer, detector, validator and scorer; "
                "does NOT measure whether the model follows injections")


def _progress(name: str, i: int, n: int, t0: float):
    if i == n or i % 10 == 0:
        print(f"  {name}: {i}/{n} ({time.time() - t0:.0f}s)", flush=True)


class Analyzer:
    """P1's pipeline (sanitize -> detect -> extract -> validate) with the extraction call cached.
    mode='oracle' replaces only the model call with the ground truth; everything else is the real code."""

    def __init__(self, mode: str = "llm"):
        from app import config
        from app.pipeline import llm
        from app.pipeline.detector import detect
        from app.pipeline.email_extract import extract_email
        from app.pipeline.extractor import extract_cv
        from app.pipeline.sanitizer import sanitize
        from app.pipeline.validator import validate
        self.model = config.OLLAMA_MODEL
        llm.TIMEOUT = EVAL_TIMEOUT  # eval measures accuracy, not latency: a slow laptop must not look like a failure
        self._sanitize, self._detect, self._validate = sanitize, detect, validate
        self._extract_cv, self._extract_email = extract_cv, extract_email
        self.cache = json.loads(CACHE_PATH.read_text(encoding="utf-8")) if CACHE_PATH.exists() else {}
        self.mode, self.calls, self.hits, self.failures = mode, 0, 0, 0

    def _cached(self, kind: str, text: str, call, model_cls):
        key = hashlib.sha256(f"{self.model}\n{kind}\n{text}".encode()).hexdigest()
        if key in self.cache:
            self.hits += 1
            return model_cls.model_validate(self.cache[key])
        self.calls += 1
        out = call(text)
        self.failures += out is None
        if out is not None:  # a failure may be transient (timeout): never cache it
            self.cache[key] = out.model_dump(mode="json")
            CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            CACHE_PATH.write_text(json.dumps(self.cache, ensure_ascii=False), encoding="utf-8")
        return out

    def cv(self, pdf_bytes: bytes, candidate_id: str, gt: dict | None = None):
        from app.contracts import CVExtraction
        san = self._sanitize(pdf_bytes)
        flags = self._detect(san.visible_text, san.hidden_findings)
        if self.mode == "oracle":
            from oracle import gt_extraction
            ext = gt_extraction(gt, san.visible_text)
        elif san.visible_text.strip():
            ext = self._cached("cv", san.visible_text, self._extract_cv, CVExtraction)
        else:
            ext = None
        return san, self._validate(candidate_id, san, ext, flags)

    def email(self, body: str, truth=None):
        from app.contracts import EmailExtraction
        if self.mode == "oracle":
            return truth
        return self._cached("email", body, self._extract_email, EmailExtraction)


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


def _attack_manifest(limit=None):
    p = CORPUS_DIR / "attacks" / "manifest.json"
    return json.loads(p.read_text(encoding="utf-8"))[:limit] if p.exists() else None


# ---------------------------------------------------------------- hidden (no LLM)


def eval_hidden(_, limit=None) -> dict:
    """Doc-level detection. Positive = attacked CV; negative = its twin or one of the 200 clean CVs.
    'strict' ignores lone undecodable-glyph findings, which P3's risk score already treats as low (H1)."""
    from app.pipeline.sanitizer import sanitize
    manifest = _attack_manifest(limit)
    if manifest is None:
        return {"skipped": "no corpus; run eval/gen_attacks.py"}
    d = CORPUS_DIR / "attacks"
    clean = sorted((GT_DIR / "pdf").glob("CV-*.pdf"))[:limit]

    def findings(pdf: bytes, strict: bool):
        fs = sanitize(pdf).hidden_findings
        return [f for f in fs if not (strict and f.channel.value == "zero_width" and UNDECODABLE.match(f.text))]

    out = {}
    for mode in ("all", "strict"):
        strict = mode == "strict"
        tp = fn = channel_ok = 0
        by_channel = {}
        for m in manifest:
            fs = findings((d / f"{m['id']}.pdf").read_bytes(), strict)
            hit = bool(fs)
            tp += hit; fn += not hit
            channel_ok += any(f.channel.value == m["expected_finding"] for f in fs)
            c = by_channel.setdefault(m["channel"], [0, 0]); c[0] += hit; c[1] += 1
        negatives = [(f"{m['id']}.twin", (d / f"{m['id']}.twin.pdf").read_bytes()) for m in manifest]
        negatives += [(p.stem, p.read_bytes()) for p in clean]
        fp_docs = []
        for name, pdf in negatives:
            fs = findings(pdf, strict)
            if fs:
                fp_docs.append({"doc": name, "channels": sorted({f.channel.value for f in fs})})
        fp = len(fp_docs)
        out[mode] = {
            "recall": rate(tp, tp + fn),
            "right_channel": rate(channel_ok, len(manifest)),
            "false_alarm_on_clean": rate(fp, len(negatives)),
            "precision": rate(tp, tp + fp),
            "by_channel_recall": {ch: rate(k, n) for ch, (k, n) in sorted(by_channel.items())},
            "false_alarm_docs": fp_docs[:30],
        }
    return out


# ---------------------------------------------------------------- attacks


def eval_attacks(an: Analyzer, limit=None) -> dict:
    manifest = _attack_manifest(limit)
    if manifest is None:
        return {"skipped": "no corpus; run eval/gen_attacks.py"}
    d = CORPUS_DIR / "attacks"
    rows, twin_scores, t0 = [], {}, time.time()
    for i, m in enumerate(manifest, 1):
        s_twin, v_twin = an.cv((d / f"{m['id']}.twin.pdf").read_bytes(), m["id"], m["ground_truth"])
        s_atk, v_atk = an.cv((d / f"{m['id']}.pdf").read_bytes(), m["id"], m["ground_truth"])
        rows.append((m, s_twin, v_twin, s_atk, v_atk))
        twin_scores.setdefault(m["job_id"], []).append(_score(v_twin, m["job_id"]))
        _progress("attacks", i, len(manifest), t0)

    success = same_text = flagged = instr_n = needs_human = 0
    by_channel, details = {}, []
    for m, s_twin, v_twin, s_atk, v_atk in rows:
        t_tw, t_atk = _score(v_twin, m["job_id"]), _score(v_atk, m["job_id"])
        pool = twin_scores[m["job_id"]]
        moved = (_fingerprint(v_twin) != _fingerprint(v_atk) or t_tw != t_atk
                 or _rank(t_tw, pool) != _rank(t_atk, pool))
        success += moved
        same = s_twin.visible_text == s_atk.visible_text
        same_text += same
        needs_human += v_atk.status == "needs_human"
        c = by_channel.setdefault(m["channel"], [0, 0]); c[0] += moved; c[1] += 1
        if m["payload_kind"] == "instruction":
            instr_n += 1
            flagged += bool(v_atk.injection_flags)
        details.append({"id": m["id"], "channel": m["channel"], "payload_kind": m["payload_kind"], "moved": moved,
                        "same_visible_text": same, "score_twin": t_tw, "score_attacked": t_atk,
                        "status_attacked": v_atk.status, "flags": len(v_atk.injection_flags)})
    n = len(rows)
    return {
        "attack_success": rate(success, n),
        "by_channel": {ch: rate(k, nn) for ch, (k, nn) in sorted(by_channel.items())},
        "visible_text_identical_to_twin": rate(same_text, n),
        "attacked_sent_to_human": rate(needs_human, n),
        "instruction_flagged": rate(flagged, instr_n),
        "details": details,
    }


# ---------------------------------------------------------------- counterfactual twins


def eval_twins(an: Analyzer, limit=None) -> dict:
    man_path = CORPUS_DIR / "twins" / "manifest.json"
    if not man_path.exists():
        return {"skipped": "no corpus; run eval/gen_twins.py"}
    manifest = json.loads(man_path.read_text(encoding="utf-8"))[:limit]
    d = CORPUS_DIR / "twins"
    scores, t0 = {}, time.time()
    for i, m in enumerate(manifest, 1):
        _, v = an.cv((d / f"{m['id']}.pdf").read_bytes(), m["id"], m["ground_truth"])
        scores[m["id"]] = (m["group"], m["variant"], _score(v, m["job_id"]), v.status)
        _progress("twins", i, len(manifest), t0)
    refs = {g: s for g, var, s, _ in scores.values() if var == "ref"}
    viol, n, by_var, details = 0, 0, {}, []
    for tid, (g, var, s, status) in scores.items():
        if var == "ref" or g not in refs:
            continue
        changed = s != refs[g]
        viol += changed; n += 1
        kind = var.split("_")[0]
        c = by_var.setdefault(kind, [0, 0]); c[0] += changed; c[1] += 1
        if changed:
            details.append({"id": tid, "variant": var, "score_ref": refs[g], "score_variant": s, "status": status})
    return {"score_changed": rate(viol, n), "by_variant": {k: rate(a, b) for k, (a, b) in sorted(by_var.items())},
            "changed_details": details}


# ---------------------------------------------------------------- emails


def eval_emails(an: Analyzer, limit=None) -> dict:
    """Lane = P3's code rules over the auth headers, the sender and the model's three enums.
    expected_lane = the same rules fed the TRUE enums from labels.json, so a lane miss is a model reading error."""
    from app.contracts import EmailExtraction
    from app.workflow import email_gate
    labels_path = EMAIL_DIR / "labels.json"
    if not labels_path.exists():
        return {"skipped": "no emails; run python -m app.workflow.demo"}
    labels = json.loads(labels_path.read_text(encoding="utf-8"))[:limit]
    verified = {c["email"].lower() for c in
                json.loads((EMAIL_DIR / "demo_candidates.json").read_text(encoding="utf-8"))}
    ok = {"intent": 0, "urgency": 0, "language": 0, "lane": 0}
    failed = unsafe = suspicious_spoof = contained = false_suspicious = 0
    spoofs = cleans = 0
    misses, t0 = [], time.time()
    for i, lab in enumerate(labels, 1):
        raw = (EMAIL_DIR / f"{lab['id']}.eml").read_bytes()
        msg = email.message_from_bytes(raw, policy=policy.default)
        auth = email_gate.authenticate(raw, msg)
        found = parseaddr(str(msg.get("From", "")))[1].lower() in verified
        truth = EmailExtraction(language=lab["language"], intent=lab["intent"], urgency=lab["urgency"])
        ext = an.email(email_gate._body_text(msg), truth)
        lane, _ = email_gate.classify(msg, auth, ext, found)
        expected, _ = email_gate.classify(msg, auth, truth, found)
        if ext is None:
            failed += 1
        else:
            ok["intent"] += ext.intent.value == lab["intent"]
            ok["urgency"] += ext.urgency.value == lab["urgency"]
            ok["language"] += ext.language.value == lab["language"]
        ok["lane"] += lane == expected
        if lane == "routine" and expected != "routine":
            unsafe += 1  # a mail that needed a human got an automatic draft
        if lab["spoofed"]:
            spoofs += 1
            suspicious_spoof += lane == "suspicious"
            contained += lane == "suspicious" or not found  # either way no candidate data is offered
        else:
            cleans += 1
            false_suspicious += lane == "suspicious"
        if lane != expected:
            misses.append({"id": lab["id"], "expected": expected, "got": lane,
                           "intent_true": lab["intent"], "intent_got": ext.intent.value if ext else None})
        _progress("emails", i, len(labels), t0)
    n, read = len(labels), len(labels) - failed
    return {
        "lane_correct": rate(ok["lane"], n),
        "unsafe_misroute": rate(unsafe, n),
        "spoof_contained": rate(contained, spoofs),
        "spoof_in_suspicious_lane": rate(suspicious_spoof, spoofs),
        "clean_marked_suspicious": rate(false_suspicious, cleans),
        "extraction_failed": rate(failed, n),
        "intent_accuracy": rate(ok["intent"], read),
        "urgency_accuracy": rate(ok["urgency"], read),
        "language_accuracy": rate(ok["language"], read),
        "lane_misses": misses,
    }


# ---------------------------------------------------------------- extraction


def eval_extraction(an: Analyzer, limit=None) -> dict:
    pdfs = sorted((GT_DIR / "pdf").glob("CV-*.pdf"))[:limit]
    if not pdfs:
        return {"skipped": "no PDFs; run eval/gen_cvs.py --count 200 --pdf"}
    tp = fp = fn = needs_human = degree_ok = 0
    yrs_err, by_lang, t0 = [], {}, time.time()
    for i, p in enumerate(pdfs, 1):
        doc = json.loads((GT_DIR / f"{p.stem}.json").read_text(encoding="utf-8"))
        gt = doc["ground_truth"]
        _, v = an.cv(p.read_bytes(), p.stem, gt)
        needs_human += v.status == "needs_human"
        got, want = {s.esco_id for s in v.skills}, set(gt["skills"])
        tp += len(got & want); fp += len(got - want); fn += len(want - got)
        c = by_lang.setdefault(gt["lang"], [0, 0, 0])
        c[0] += len(got & want); c[1] += len(got - want); c[2] += len(want - got)
        yrs_err.append(abs(v.years_experience - gt["years_experience"]))
        degree_ok += v.highest_degree.value == gt["degree"]["level"]
        _progress("extraction", i, len(pdfs), t0)
    return {"n_docs": len(pdfs), "skills": prf(tp, fp, fn),
            "skills_by_lang": {k: prf(*c) for k, c in sorted(by_lang.items())},
            "years_mae": round(sum(yrs_err) / len(yrs_err), 2),
            "degree_correct": rate(degree_ok, len(pdfs)),
            "sent_to_human": rate(needs_human, len(pdfs))}


SECTIONS = {"hidden": eval_hidden, "attacks": eval_attacks, "twins": eval_twins,
            "emails": eval_emails, "extraction": eval_extraction}


def _write(summary: dict):
    baseline = RESULTS_DIR / "baseline.json"
    summary["baseline"] = json.loads(baseline.read_text(encoding="utf-8")) if baseline.exists() else {
        "skipped": "run eval/baselines.py"}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=",".join(SECTIONS))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--extraction", choices=("auto", "llm", "oracle"), default="auto")
    a = ap.parse_args()
    from app import config
    from app.pipeline.demo import _ollama_ready
    mode = a.extraction
    if mode == "auto":
        mode = "llm" if _ollama_ready() else "oracle"
    if mode == "llm" and set(a.only.split(",")) - {"hidden"} and not _ollama_ready():
        raise SystemExit("LLM mode requested but the model is not reachable; nothing written. "
                         "Start Ollama (or set HG_OLLAMA_HOSTS) or run with --extraction oracle")
    summary = json.loads(SUMMARY.read_text(encoding="utf-8")) if SUMMARY.exists() else {}
    summary.setdefault("sections", {})
    summary.update({"generated_at": datetime.now(timezone.utc).isoformat(), "model": config.OLLAMA_MODEL,
                    "groq_fallback": config.GROQ_FALLBACK})
    an = None
    for name in a.only.split(","):
        if name != "hidden" and an is None:
            an = Analyzer(mode)
        t0 = time.time()
        print(f"[{name}] start", flush=True)
        res = SECTIONS[name](an, a.limit)
        res |= {"seconds": round(time.time() - t0, 1), "limit": a.limit,
                "finished_at": datetime.now(timezone.utc).isoformat()}
        res["extraction_mode"] = "none (sanitizer only)" if name == "hidden" else mode
        if name != "hidden" and mode == "oracle":
            res["scope"] = ORACLE_SCOPE
        if an is not None and mode == "llm":
            res["llm_calls_total"], res["llm_cache_hits_total"] = an.calls, an.hits
            res["llm_failed_calls_total"] = an.failures  # a model that died mid-run shows up here, not as 0/40
        summary["sections"][name] = res
        _write(summary)
        print(f"[{name}] done", json.dumps({k: (v.get("text") if isinstance(v, dict) and "text" in v else v)
                                            for k, v in res.items() if not k.endswith(("details", "docs", "misses"))},
                                           ensure_ascii=False)[:900], flush=True)
    print(f"wrote {SUMMARY}")


if __name__ == "__main__":
    main()
