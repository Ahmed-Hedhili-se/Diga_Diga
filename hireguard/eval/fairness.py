"""Group fairness and proxy audit (P2). Complements the twins test.

    python eval/fairness.py [--extraction auto|llm|oracle] [--k-frac 0.2] [--perm 2000]

Twins prove individual invariance: change one attribute, the score must not move. They cannot see bias
that rides on fields the scorer is allowed to use (a degree requirement that only one school's graduates
meet, an extraction step that loses Arabic skills). This audit looks at groups instead:

1. Selection rates. Within each job the top k_frac of candidates are "shortlisted". For each attribute
   (region, school, gender, CV language) we report each group's selection rate and the adverse-impact
   ratio AIR = lowest rate / highest rate (four-fifths rule: AIR < 0.8 is a warning). Small samples make
   AIR noisy, so every AIR comes with a job-stratified permutation p-value and a bootstrap 95% interval.
   Verdict: "flag" = AIR < 0.8 and p < 0.05; "watch" = AIR < 0.8 but not significant; "ok" otherwise.
2. Proxy test. Can the attribute be predicted from the scored features alone (skills and years, total
   years, degree, language levels)? Cross-validated macro AUC vs. a label-shuffled null. A proxy means
   the attribute can leak into scores through allowed fields.
3. Gap decomposition. For the lowest- and highest-selected groups, which score component carries the gap.
4. Positive control. A copy of the data where the degree depends on the school (SUP'COM -> engineering
   degree, ISET -> licence), scored with a planted criterion: every rubric requires an engineering degree
   and the degree component weighs 30 instead of 10. The audit must flag school here, or it is not
   sensitive enough to trust on the real data.

Writes eval/results/fairness.json (served by GET /api/eval/fairness). All data is fictional.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import random
from datetime import datetime, timezone

import numpy as np

from common import GT_DIR, RESULTS_DIR, SKILLS
from gen_cvs import finalize, render_text
from harness import ORACLE_SCOPE, _load_pipeline
from render import text_pdf

REGION = {"La Marsa": "Grand Tunis", "Ariana": "Grand Tunis", "Sfax": "coast", "Sousse": "coast",
          "Bizerte": "coast", "Gabès": "coast", "Kasserine": "interior", "Tataouine": "interior"}
ATTRS = {
    "region": lambda gt: REGION.get(gt["town"], "other"),
    "school": lambda gt: gt["school"],
    "gender": lambda gt: gt["gender"],
    "cv_language": lambda gt: gt["lang"],
}
MIN_GROUP = 10            # groups smaller than this are listed but not used for AIR
CEFR_RANK = {"A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6, "native": 7}
DEGREE_RANK = {"none": 0, "bac": 1, "bts": 2, "licence": 3, "master": 4, "ingenieur": 5, "phd": 6}
SKILL_IDS = sorted(SKILLS)


# ---------------------------------------------------------------- data
def load_gts() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8"))["ground_truth"] for p in sorted(GT_DIR.glob("CV-*.json"))]


def run_pipeline(gts: list[dict], analyze, rubric_for=None) -> list[dict]:
    from app.scoring.jobs import file_rubric
    from app.scoring.scorer import score

    rubric_for = rubric_for or file_rubric
    rows = []
    for gt in gts:
        pdf = text_pdf(render_text(gt), gt["lang"]).tobytes()
        _, v = analyze(pdf, gt["id"], gt)
        s = score(v, rubric_for(gt["job_id"]))
        rows.append({"id": gt["id"], "job": gt["job_id"], "total": s.total,
                     "components": {c.name: c.points for c in s.components},
                     "features": features(v), **{a: f(gt) for a, f in ATTRS.items()}})
    return rows


def features(v) -> list[float]:
    years = {s.esco_id: s.years for s in v.skills}
    langs = {l.iso.value: CEFR_RANK.get(l.cefr.value, 0) for l in v.languages}
    return ([1.0 if sid in years else 0.0 for sid in SKILL_IDS] + [years.get(sid, 0.0) for sid in SKILL_IDS]
            + [v.years_experience, DEGREE_RANK.get(v.highest_degree.value, 0)]
            + [langs.get(iso, 0) for iso in ("fr", "en", "ar")])


def shortlist(rows: list[dict], k_frac: float) -> None:
    """Marks the top ceil(k_frac * n) of each job as selected (ties broken by id, deterministic)."""
    for job in {r["job"] for r in rows}:
        rs = sorted((r for r in rows if r["job"] == job), key=lambda r: (-r["total"], r["id"]))
        k = max(1, math.ceil(k_frac * len(rs)))
        for i, r in enumerate(rs):
            r["selected"] = i < k


# ---------------------------------------------------------------- statistics
def _air(sel: np.ndarray, grp: np.ndarray, groups: list[str]) -> float:
    rates = [sel[grp == g].mean() for g in groups]
    return min(rates) / max(rates) if max(rates) > 0 else 1.0


def _strata_perm(grp: np.ndarray, jobs: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    out = grp.copy()
    for j in np.unique(jobs):
        idx = np.flatnonzero(jobs == j)
        out[idx] = grp[rng.permutation(idx)]
    return out


def selection_audit(rows: list[dict], attr: str, n_perm: int, rng: np.random.Generator) -> dict:
    sel = np.array([r["selected"] for r in rows], dtype=float)
    grp = np.array([r[attr] for r in rows])
    jobs = np.array([r["job"] for r in rows])
    sizes = {g: int((grp == g).sum()) for g in sorted(set(grp))}
    groups = [g for g, n in sizes.items() if n >= MIN_GROUP]
    per_group = {g: {"n": sizes[g], "selected": int(sel[grp == g].sum()),
                     "rate": round(float(sel[grp == g].mean()), 3)} for g in sizes}
    if len(groups) < 2:
        return {"groups": per_group, "verdict": "n/a", "note": f"fewer than 2 groups with n >= {MIN_GROUP}"}
    obs = _air(sel, grp, groups)
    perm = np.array([_air(sel, _strata_perm(grp, jobs, rng), groups) for _ in range(n_perm)])
    p = float((np.sum(perm <= obs) + 1) / (n_perm + 1))
    boots = []
    for _ in range(n_perm):
        idx = np.concatenate([rng.choice(np.flatnonzero(jobs == j), size=int((jobs == j).sum()))
                              for j in np.unique(jobs)])
        g2, s2 = grp[idx], sel[idx]
        if all((g2 == g).any() for g in groups):
            boots.append(_air(s2, g2, groups))
    lo, hi = np.percentile(boots, [2.5, 97.5]) if boots else (float("nan"), float("nan"))
    rates = {g: sel[grp == g].mean() for g in groups}
    low, high = min(rates, key=rates.get), max(rates, key=rates.get)
    verdict = "ok" if obs >= 0.8 else ("flag" if p < 0.05 else "watch")
    return {"groups": per_group, "air": round(obs, 3), "air_ci95": [round(lo, 3), round(hi, 3)],
            "p_value": round(p, 4), "lowest": low, "highest": high, "verdict": verdict,
            "gap_by_component": gap_components(rows, attr, low, high)}


def gap_components(rows: list[dict], attr: str, low: str, high: str) -> dict:
    """Mean points per component, highest-selected minus lowest-selected group, and each share of the gap."""
    def mean(g, c):
        xs = [r["components"][c] for r in rows if r[attr] == g]
        return sum(xs) / len(xs)
    comps = list(rows[0]["components"])
    diff = {c: mean(high, c) - mean(low, c) for c in comps}
    total = sum(diff.values())
    return {c: {"points": round(d, 2), "share": round(d / total, 2) if abs(total) > 1e-9 else None}
            for c, d in diff.items()}


def proxy_test(rows: list[dict], attr: str, n_null: int, seed: int) -> dict:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    x = np.array([r["features"] for r in rows])
    y = np.array([r[attr] for r in rows])
    keep = np.isin(y, [g for g in set(y) if (y == g).sum() >= MIN_GROUP])
    x, y = x[keep], y[keep]
    classes = sorted(set(y))
    if len(classes) < 2:
        return {"auc": None, "note": "fewer than 2 groups"}

    def auc(labels):
        model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=0.5))
        cv = StratifiedKFold(5, shuffle=True, random_state=seed)
        prob = cross_val_predict(model, x, labels, cv=cv, method="predict_proba")
        if len(classes) == 2:
            return roc_auc_score(labels == classes[1], prob[:, 1])
        return roc_auc_score(labels, prob, multi_class="ovr", average="macro", labels=classes)

    obs = auc(y)
    rng = np.random.default_rng(seed)
    null = [auc(rng.permutation(y)) for _ in range(n_null)]
    null95 = float(np.percentile(null, 95))
    return {"auc": round(float(obs), 3), "null_auc_95th": round(null95, 3),
            "proxy": bool(obs > null95 and obs >= 0.6)}


def audit(rows: list[dict], k_frac: float, n_perm: int, n_null: int, seed: int) -> dict:
    shortlist(rows, k_frac)
    rng = np.random.default_rng(seed)
    return {a: selection_audit(rows, a, n_perm, rng) | {"proxy": proxy_test(rows, a, n_null, seed)} for a in ATTRS}


# ---------------------------------------------------------------- positive control
def planted_rubric(job_id: str):
    """The planted biased criterion: an engineering degree, required everywhere and weighted 30."""
    from app.contracts import DegreeLevel
    from app.scoring.jobs import file_rubric

    r = file_rubric(job_id)
    return r.model_copy(update={"required_degree": DegreeLevel.ingenieur,
                                "component_weights": {**r.component_weights, "degree": 30}})


def biased_world(gts: list[dict], seed: int) -> list[dict]:
    """Degree level follows the school, as in reality: the audit must catch the resulting school gap."""
    rng = random.Random(seed)
    out = []
    for gt in gts:
        g = copy.deepcopy(gt)
        g["degree"]["level"] = {"supcom": "ingenieur", "iset": "licence",
                                "private": rng.choice(["ingenieur", "master"])}[g["school"]]
        out.append(finalize(g))
    return out


# ---------------------------------------------------------------- report
def _line(attr: str, a: dict) -> str:
    if a.get("verdict") == "n/a":
        return f"  {attr:<12} n/a ({a['note']})"
    rates = ", ".join(f"{g} {v['selected']}/{v['n']}" for g, v in a["groups"].items())
    px = a["proxy"]
    return (f"  {attr:<12} AIR {a['air']:.2f} [{a['air_ci95'][0]:.2f}-{a['air_ci95'][1]:.2f}] p={a['p_value']:.3f} "
            f"-> {a['verdict'].upper():<5} | proxy AUC {px['auc']} (null95 {px['null_auc_95th']}) | {rates}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extraction", choices=["auto", "llm", "oracle"], default="auto")
    ap.add_argument("--k-frac", type=float, default=0.2)
    ap.add_argument("--perm", type=int, default=2000)
    ap.add_argument("--null", type=int, default=30)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    analyze, mode = _load_pipeline(a.extraction)
    if isinstance(analyze, str):
        raise SystemExit(analyze)
    gts = load_gts()
    if not gts:
        raise SystemExit("no ground truth; run eval/gen_cvs.py --count 200")

    observed = audit(run_pipeline(gts, analyze), a.k_frac, a.perm, a.null, a.seed)
    control = audit(run_pipeline(biased_world(gts, a.seed), analyze, planted_rubric), a.k_frac, a.perm, a.null,
                    a.seed)
    control_ok = control["school"]["verdict"] == "flag" and control["school"]["proxy"]["proxy"]
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "extraction_mode": mode, "scope": ORACLE_SCOPE if mode == "oracle" else "end to end with the LLM",
        "n_cvs": len(gts), "k_frac": a.k_frac, "permutations": a.perm,
        "rules": {"flag": "AIR < 0.8 and permutation p < 0.05", "watch": "AIR < 0.8, not significant",
                  "proxy": "CV macro AUC above the 95th percentile of shuffled labels and >= 0.6"},
        "observed": observed,
        "positive_control": {"design": "degree follows school; planted criterion: engineering degree required, "
                                       "degree component weight 30",
                             "school": control["school"], "detected": control_ok},
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "fairness.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"extraction: {mode}  n={len(gts)}  shortlist = top {a.k_frac:.0%} per job")
    print("observed (synthetic CVs):")
    for attr, res in observed.items():
        print(_line(attr, res))
    print("positive control (degree follows school):")
    print(_line("school", control["school"]))
    print(f"  gap by component: {control['school']['gap_by_component']}")
    print(f"  control detected: {control_ok}")
    print(f"wrote {RESULTS_DIR / 'fairness.json'}")


if __name__ == "__main__":
    main()
