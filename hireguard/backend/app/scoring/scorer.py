"""Deterministic scorer (P2). Code decides; the model never sees or sets a score.

Input is ValidatedCV only: ESCO ids, computed years, degree enum, ISO+CEFR languages and
evidence spans. Name, town, school, gender and injection flags are not inputs to any formula
(injection_flag_count is passed through for display only).
"""
from __future__ import annotations

from ..contracts import (
    CEFR_ORDER,
    DEGREE_ORDER,
    Rubric,
    ScoreComponent,
    ScoreOutput,
    Span,
    ValidatedCV,
)

COMPONENTS = ("skills", "experience", "degree", "languages")

# A matched skill earns SKILL_BASE of its weight for being evidenced, the rest grows
# linearly with years used, capped at SKILL_FULL_YEARS.
SKILL_BASE = 0.6
# A skill that only appears in a list, with no dated job using it, is what keyword stuffing looks like:
# it earns at most this share of what a dated-experience skill earns.
LISTED_ONLY_FACTOR = 0.3
SKILL_FULL_YEARS = 4.0

LANG_NAMES = {"fr": "French", "en": "English", "ar": "Arabic", "de": "German", "es": "Spanish", "it": "Italian"}


def _label(esco_id: str) -> str:
    return esco_id.replace("-", " ").capitalize()


def _component_max(rubric: Rubric) -> dict[str, float]:
    raw = {c: max(0.0, float(rubric.component_weights.get(c, 0))) for c in COMPONENTS}
    total = sum(raw.values())
    if total <= 0:
        return {c: 100 / len(COMPONENTS) for c in COMPONENTS}
    return {c: 100 * w / total for c, w in raw.items()}


def _skills(cv: ValidatedCV, rubric: Rubric, max_pts: float) -> ScoreComponent:
    weights = {k: max(0.0, float(w)) for k, w in rubric.skill_weights.items()}
    wsum = sum(weights.values())
    found = {}
    for s in cv.skills:  # keep the best-evidenced entry per skill
        if s.esco_id not in found or s.years > found[s.esco_id].years:
            found[s.esco_id] = s
    if wsum <= 0:
        return ScoreComponent(name="skills", points=max_pts, max_points=max_pts,
                              justifications=["No skills required by rubric"])
    # justifications[i] pairs with evidence[i] (UI click-to-highlight); unevidenced lines come after
    earned, just, ev, missing = 0.0, [], [], []
    for esco_id, w in sorted(weights.items(), key=lambda kv: (-kv[1], kv[0])):
        s = found.get(esco_id)
        if s is None:
            missing.append(f"{_label(esco_id)}: not evidenced in visible text")
            continue
        yrs = max(0.0, s.years)
        frac = SKILL_BASE + (1 - SKILL_BASE) * min(yrs, SKILL_FULL_YEARS) / SKILL_FULL_YEARS
        listed = s.support == "listed_only"
        earned += w * frac * (LISTED_ONLY_FACTOR if listed else 1.0)
        just.append(f"{s.label}: {yrs:.1f} yrs, see p.{s.page + 1}"
                    + (f", only listed, no dated job uses it (counts {round(100 * LISTED_ONLY_FACTOR)}%)" if listed else ""))
        ev.append(s.evidence)
    return ScoreComponent(name="skills", points=max_pts * earned / wsum, max_points=max_pts,
                          justifications=just + missing, evidence=ev)


def _experience(cv: ValidatedCV, rubric: Rubric, max_pts: float) -> ScoreComponent:
    yrs = max(0.0, cv.years_experience)
    frac = 1.0 if rubric.min_years <= 0 else min(1.0, yrs / rubric.min_years)
    return ScoreComponent(
        name="experience", points=max_pts * frac, max_points=max_pts,
        justifications=[f"Experience: {yrs:.1f} yrs computed from dates (minimum {rubric.min_years:g})"],
    )


def _degree(cv: ValidatedCV, rubric: Rubric, max_pts: float) -> ScoreComponent:
    have = DEGREE_ORDER.index(cv.highest_degree.value)
    need = DEGREE_ORDER.index(rubric.required_degree.value)
    frac = 1.0 if have >= need else have / need
    ev: list[Span] = [cv.degree_evidence] if cv.degree_evidence else []
    where = ", see evidence" if ev else ""
    return ScoreComponent(
        name="degree", points=max_pts * frac, max_points=max_pts,
        justifications=[f"Degree: {cv.highest_degree.value} (required {rubric.required_degree.value}){where}"],
        evidence=ev,
    )


def _languages(cv: ValidatedCV, rubric: Rubric, max_pts: float) -> ScoreComponent:
    if not rubric.languages:
        return ScoreComponent(name="languages", points=max_pts, max_points=max_pts,
                              justifications=["No language requirement"])
    have = {}
    for l in cv.languages:
        have[l.iso.value] = max(have.get(l.iso.value, -1), CEFR_ORDER.index(l.cefr.value))
    fracs, just = [], []
    for req in rubric.languages:
        need = CEFR_ORDER.index(req.min_cefr.value)
        got = have.get(req.iso.value, -1)
        fracs.append(1.0 if got >= need else (got + 1) / (need + 1))
        level = CEFR_ORDER[got] if got >= 0 else "not stated"
        just.append(f"{LANG_NAMES.get(req.iso.value, req.iso.value)}: {level} (required {req.min_cefr.value})")
    return ScoreComponent(name="languages", points=max_pts * sum(fracs) / len(fracs), max_points=max_pts,
                          justifications=just)


def score(validated: ValidatedCV, rubric: Rubric) -> ScoreOutput:
    mx = _component_max(rubric)
    comps = [
        _skills(validated, rubric, mx["skills"]),
        _experience(validated, rubric, mx["experience"]),
        _degree(validated, rubric, mx["degree"]),
        _languages(validated, rubric, mx["languages"]),
    ]
    for c in comps:
        c.points = round(c.points, 2)
        c.max_points = round(c.max_points, 2)
    total = round(min(100.0, max(0.0, sum(c.points for c in comps))), 1)
    return ScoreOutput(
        candidate_id=validated.candidate_id,
        job_id=rubric.job_id,
        total=total,
        components=comps,
        status="proposed",
        needs_human=validated.status == "needs_human",
        injection_flag_count=len(validated.injection_flags),
    )
