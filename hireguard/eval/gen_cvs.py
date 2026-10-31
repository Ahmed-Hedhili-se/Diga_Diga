"""Generate synthetic CVs from ground-truth JSON (P2).

    python eval/gen_cvs.py --count 200 [--pdf] [--seed 7]

Writes data/cv_ground_truth/CV-XXXX.json = {"ground_truth": {...}, "text": "..."}
and, with --pdf, data/cv_ground_truth/pdf/CV-XXXX.pdf. Everything is fictional.
"""
from __future__ import annotations

import argparse
import copy
import json
import random

from common import (DEGREE_TEXT, LANG_NAMES, EMPLOYERS, FIRST_NAMES, GT_DIR, JOB_SKILLS, LAST_NAMES,
                    SCHOOLS, SKILLS, TOWNS)

LANG_MIX = ["fr"] * 5 + ["en"] * 3 + ["ar"] * 2
CEFR = ["B1", "B2", "C1", "C2", "native"]

HEAD = {
    "fr": {"exp": "EXPÉRIENCE PROFESSIONNELLE", "edu": "FORMATION", "skills": "COMPÉTENCES", "lang": "LANGUES",
           "now": "aujourd'hui", "used": "outils"},
    "en": {"exp": "PROFESSIONAL EXPERIENCE", "edu": "EDUCATION", "skills": "SKILLS", "lang": "LANGUAGES",
           "now": "present", "used": "tools"},
    "ar": {"exp": "الخبرة المهنية", "edu": "التكوين", "skills": "المهارات", "lang": "اللغات",
           "now": "حاليا", "used": "الأدوات"},
}
ROLE = {
    "JOB-DATA-01": {"fr": ("Ingénieur données", "Ingénieure données"), "en": ("Data engineer", "Data engineer"),
                    "ar": ("مهندس بيانات", "مهندسة بيانات")},
    "JOB-FS-02": {"fr": ("Développeur full-stack", "Développeuse full-stack"),
                  "en": ("Full-stack developer", "Full-stack developer"),
                  "ar": ("مطور ويب", "مطورة ويب")},
    "JOB-HR-03": {"fr": ("Assistant RH", "Assistante RH"), "en": ("HR assistant", "HR assistant"),
                  "ar": ("مساعد موارد بشرية", "مساعدة موارد بشرية")},
}
LEVEL_TEXT = {"native": {"fr": "langue maternelle", "en": "native", "ar": "اللغة الأم"}}


def _ym(y: int, m: int) -> str:
    return f"{y:04d}-{m:02d}"


def _months(a: str, b: str) -> int:
    ya, ma = map(int, a.split("-"))
    yb, mb = map(int, b.split("-"))
    return (yb - ya) * 12 + (mb - ma)


def skill_years(gt: dict, as_of: str = "2026-10") -> dict[str, float]:
    """Ground-truth years per skill: union of months over the experiences that list it."""
    months: dict[str, set[int]] = {}
    for e in gt["experiences"]:
        end = e["end"] or as_of
        y, m = map(int, e["start"].split("-"))
        for i in range(_months(e["start"], end)):
            idx = (y * 12 + m - 1) + i
            for s in e["skills"]:
                months.setdefault(s, set()).add(idx)
    return {s: round(len(v) / 12, 1) for s, v in months.items()}


def total_years(gt: dict, as_of: str = "2026-10") -> float:
    covered = set()
    for e in gt["experiences"]:
        y, m = map(int, e["start"].split("-"))
        covered.update(range(y * 12 + m - 1, y * 12 + m - 1 + _months(e["start"], e["end"] or as_of)))
    return round(len(covered) / 12, 1)


def make_gt(i: int, rng: random.Random) -> dict:
    job = rng.choice(list(JOB_SKILLS))
    lang = rng.choice(LANG_MIX)
    gender = rng.choice(["f", "m"])
    pool = JOB_SKILLS[job] + rng.sample([s for s in SKILLS if s not in JOB_SKILLS[job]], 2)
    n_exp = rng.choice([0, 1, 1, 2, 2, 3])
    level = rng.choice(["licence", "master", "ingenieur"] if job != "JOB-HR-03" else ["licence", "licence", "master"])
    grad_year = rng.randint(2014, 2024)
    exps, y, m = [], grad_year, rng.randint(7, 12)
    for k in range(n_exp):
        dur = rng.randint(8, 40)
        end_idx = y * 12 + m - 1 + dur
        end = None if k == n_exp - 1 and rng.random() < 0.6 else _ym(end_idx // 12, end_idx % 12 + 1)
        if end and end > "2026-10":
            end = None
        exps.append({"employer": rng.choice(EMPLOYERS), "start": _ym(y, m), "end": end,
                     "skills": sorted(rng.sample(pool, rng.randint(2, min(5, len(pool)))))})
        if end is None:
            break
        nxt = end_idx + rng.randint(0, 4)
        y, m = nxt // 12, nxt % 12 + 1
        if _ym(y, m) >= "2026-10":
            break
    langs = [{"iso": "ar", "cefr": "native"}, {"iso": "fr", "cefr": rng.choice(CEFR[:4])},
             {"iso": "en", "cefr": rng.choice(CEFR[:4])}]
    gt = {
        "id": f"CV-{i:04d}", "job_id": job, "lang": lang, "gender": gender,
        "name": f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
        "town": rng.choice(TOWNS), "school": rng.choice(list(SCHOOLS)),
        "degree": {"level": level, "year": grad_year},
        "experiences": exps,
        "extra_skills": sorted(rng.sample(pool, 2)),  # listed in the skills section only
        "languages": langs,
    }
    gt["email"] = gt["name"].lower().replace(" ", ".") + f"{i}@example.tn"
    return finalize(gt)


def finalize(gt: dict) -> dict:
    """Recompute derived ground truth after any edit (twins reuse this)."""
    gt["skills"] = sorted(set(gt["extra_skills"]) | {s for e in gt["experiences"] for s in e["skills"]})
    gt["skill_years"] = skill_years(gt)
    gt["years_experience"] = total_years(gt)
    return gt


def render_text(gt: dict) -> str:
    L, h = gt["lang"], HEAD[gt["lang"]]
    f = 1 if gt["gender"] == "f" else 0
    role = ROLE[gt["job_id"]][L][f]  # gendered title: the ingénieur/ingénieure twin flips this
    lab = lambda s: SKILLS[s][L]
    lines = [gt["name"], role, f"{gt['email']} | {gt['town']}", "", h["exp"]]
    mmyyyy = lambda ym: f"{ym[5:]}/{ym[:4]}"  # CV shows 09/2021; ground truth keeps 2021-09
    for e in gt["experiences"]:
        end = mmyyyy(e["end"]) if e["end"] else h["now"]
        lines.append(f"{mmyyyy(e['start'])} – {end} : {e['employer']}")
        lines.append(f"  {h['used']}: " + ", ".join(lab(s) for s in e["skills"]))
    lines += ["", h["edu"],
              f"{DEGREE_TEXT[gt['degree']['level']][L]}, {SCHOOLS[gt['school']][L]}, {gt['degree']['year']}",
              "", h["skills"], ", ".join(lab(s) for s in gt["skills"]), "", h["lang"]]
    for l in gt["languages"]:
        lvl = LEVEL_TEXT.get(l["cefr"], {}).get(L, l["cefr"])
        lines.append(f"{LANG_NAMES[L][l['iso']]} : {lvl}")
    return "\n".join(lines)


def write(gt: dict, out_dir=GT_DIR, pdf: bool = False):
    out_dir.mkdir(parents=True, exist_ok=True)
    text = render_text(gt)
    (out_dir / f"{gt['id']}.json").write_text(
        json.dumps({"ground_truth": gt, "text": text}, ensure_ascii=False, indent=1), encoding="utf-8")
    if pdf:
        from render import text_pdf
        (out_dir / "pdf").mkdir(exist_ok=True)
        text_pdf(text, gt["lang"]).save(out_dir / "pdf" / f"{gt['id']}.pdf")


def generate(count: int, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    return [make_gt(i + 1, rng) for i in range(count)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=20, help="200 for the full extraction-F1 set")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--pdf", action="store_true")
    a = ap.parse_args()
    for gt in generate(a.count, a.seed):
        write(copy.deepcopy(gt), pdf=a.pdf)
    print(f"wrote {a.count} CVs to {GT_DIR}")


if __name__ == "__main__":
    main()
