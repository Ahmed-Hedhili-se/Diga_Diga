"""Team-aware rubric suggestions (P2). Code proposes, HR decides.

A role joins a team. If nobody on that team holds a skill its work needs (gap), or only one person does
(single holder, a key-person risk), hiring for that skill is a job-related reason to weight it higher.
This module turns the team's skill coverage into a *proposed* rubric. Nothing changes until an
hr_manager saves it through PUT /jobs/{id}/rubric, which is audited like any other rubric edit.

Rules (transparent, no learning; weights rounded to 0.5):
  gap (0 holders)            weight x1.5 (at least +1), or added with weight 2 if the rubric does not list it
  single holder (1 holder)   weight x1.25 (at least +0.5), or added with weight 1
  covered (2+ holders)       unchanged
Team rosters live in data/team/teams.json (fictional). In production they would come from consented,
employee-editable skills profiles, and only skill counts per team leave that store.
"""
from __future__ import annotations

import json
from functools import lru_cache

from ..config import DATA_DIR
from ..contracts import Rubric, ValidatedCV
from ..pipeline.esco import load_esco

TEAMS_PATH = DATA_DIR / "team" / "teams.json"
GAP_FACTOR, SINGLE_FACTOR = 1.5, 1.25
GAP_NEW_WEIGHT, SINGLE_NEW_WEIGHT = 2.0, 1.0


@lru_cache(maxsize=1)
def load_teams() -> dict[str, dict]:
    data = json.loads(TEAMS_PATH.read_text(encoding="utf-8"))
    return {t["job_id"]: t for t in data["teams"]}


def _round_half(x: float) -> float:
    return round(x * 2) / 2


def coverage(team: dict) -> list[dict]:
    esco = load_esco()
    needed = list(dict.fromkeys(team["work_requires"]))
    out = []
    for sid in needed:
        holders = [m for m in team["members"] if sid in m["skills"]]
        verified = [m for m in holders if sid in m.get("verified", [])]
        n = len(holders)
        out.append({"esco_id": sid, "label": esco.get(sid, {}).get("label", sid), "holders": n,
                    "verified_holders": len(verified),
                    "status": "gap" if n == 0 else "single_holder" if n == 1 else "covered"})
    return out


def suggest(rubric: Rubric, team: dict) -> tuple[Rubric, list[dict]]:
    weights = dict(rubric.skill_weights)
    size = len(team["members"])
    diff = []
    for c in coverage(team):
        if c["status"] == "covered":
            continue
        sid = c["esco_id"]
        before = weights.get(sid)
        if before is None:
            after = GAP_NEW_WEIGHT if c["status"] == "gap" else SINGLE_NEW_WEIGHT
        elif c["status"] == "gap":
            after = max(before + 1, _round_half(before * GAP_FACTOR))
        else:  # rounding must not swallow the suggestion for small weights
            after = max(before + 0.5, _round_half(before * SINGLE_FACTOR))
        if after == before:
            continue
        who = "no one" if c["holders"] == 0 else "only one person"
        diff.append({"esco_id": sid, "label": c["label"], "before": before, "after": after, "status": c["status"],
                     "reason": f"{who} on the {team['name']} holds {c['label']} ({c['holders']} of {size})"})
        weights[sid] = after
    return rubric.model_copy(update={"skill_weights": weights}), diff


def team_gaps(job_id: str, rubric: Rubric, cvs: list[ValidatedCV]) -> dict | None:
    team = load_teams().get(job_id)
    if team is None:
        return None
    cov = coverage(team)
    proposed, diff = suggest(rubric, team)
    flagged = {c["esco_id"]: c["label"] for c in cov if c["status"] != "covered"}
    fills = {}
    for v in cvs:
        hit = [flagged[s.esco_id] for s in v.skills if s.esco_id in flagged]
        if hit:
            fills[v.candidate_id] = sorted(hit)
    return {"job_id": job_id, "team": team["name"], "team_size": len(team["members"]),
            "coverage": cov, "diff": diff, "proposed_rubric": proposed.model_dump(mode="json"),
            "candidates_filling_gaps": fills}
