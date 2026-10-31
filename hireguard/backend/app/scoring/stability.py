"""Shortlist stability (P2): how fragile is each candidate's place in the top k?

Rubric weights are HR's judgement, not physical constants. If a modest change in those weights moves a
candidate across the shortlist cut-off, that decision is fragile and deserves a careful human look.

Monte Carlo, pure code: every skill weight and component weight is multiplied by an independent factor
drawn uniformly from [1 - jitter, 1 + jitter], candidates are re-scored and re-ranked. Ties are broken at
random within each draw: two identical profiles at the cut-off are a coin flip, not "stable" because one
id sorts first. Seeded, so the same inputs always give the same badges.

  stable_in   in the top k in >= 90% of draws
  stable_out  in the top k in <= 10% of draws
  borderline  everything in between: review this decision one by one
"""
from __future__ import annotations

import random

from ..contracts import Rubric, ValidatedCV
from .scorer import score

STABLE_IN, STABLE_OUT = 0.9, 0.1
DEFAULT_DRAWS, DEFAULT_JITTER = 300, 0.15


def _jitter(rubric: Rubric, rng: random.Random, j: float) -> Rubric:
    data = rubric.model_dump()
    data["skill_weights"] = {k: w * rng.uniform(1 - j, 1 + j) for k, w in rubric.skill_weights.items()}
    data["component_weights"] = {k: w * rng.uniform(1 - j, 1 + j) for k, w in rubric.component_weights.items()}
    return Rubric.model_validate(data)


def _order(totals: dict[str, float], rng: random.Random | None = None) -> list[str]:
    if rng is None:  # the displayed ranking: deterministic, ties by id
        return sorted(totals, key=lambda c: (-totals[c], c))
    tiebreak = {c: rng.random() for c in sorted(totals)}
    return sorted(totals, key=lambda c: (-round(totals[c], 6), tiebreak[c]))


def stability(cvs: list[ValidatedCV], rubric: Rubric, k: int, draws: int = DEFAULT_DRAWS,
              jitter: float = DEFAULT_JITTER, seed: int = 7) -> list[dict]:
    if not cvs:
        return []
    k = max(1, min(k, len(cvs)))
    rng = random.Random(seed)
    base = _order({v.candidate_id: score(v, rubric).total for v in cvs})
    ranks: dict[str, list[int]] = {c: [] for c in base}
    for _ in range(draws):
        r = _jitter(rubric, rng, jitter)
        for pos, c in enumerate(_order({v.candidate_id: score(v, r).total for v in cvs}, rng), start=1):
            ranks[c].append(pos)
    out = []
    for base_rank, c in enumerate(base, start=1):
        rs = sorted(ranks[c])
        p = sum(1 for x in rs if x <= k) / draws
        out.append({
            "candidate_id": c, "base_rank": base_rank, "p_top_k": round(p, 3),
            "rank_p05": rs[int(0.05 * (draws - 1))], "rank_p95": rs[int(0.95 * (draws - 1))],
            "label": "stable_in" if p >= STABLE_IN else "stable_out" if p <= STABLE_OUT else "borderline",
        })
    return out
