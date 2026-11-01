"""Scoring, eval and money endpoints (P2). Paths frozen in contracts/API.md."""
from __future__ import annotations

import json
import math
import re
import sqlite3
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, conlist

from ..config import ROOT
from ..contracts import ApprovalItem, ApprovalKind, Role, Rubric, ScoreOutput, UserOut
from ..auth.core import require_roles
from ..db import connect, register_schema
from ..workflow.audit import append as audit_append
from . import jobs, money, offer_fit, rediscover
from .scorer import score
from .stability import DEFAULT_DRAWS, stability
from .team_gaps import team_gaps

router = APIRouter()

RM = require_roles(Role.recruiter, Role.hr_manager)
M = require_roles(Role.hr_manager)
MA = require_roles(Role.hr_manager, Role.admin)

EVAL_SUMMARY = ROOT / "eval" / "results" / "summary.json"
EVAL_FAIRNESS = ROOT / "eval" / "results" / "fairness.json"


def _validated(job_id: str):
    try:
        from ..pipeline import service  # P1
        return service.list_validated(job_id)
    except (ImportError, AttributeError):
        raise HTTPException(501, "pipeline.service.list_validated not available yet")


@register_schema
def _schema(conn: sqlite3.Connection):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS score_results (
            candidate_id TEXT NOT NULL,
            job_id TEXT NOT NULL,
            score_json TEXT NOT NULL,
            PRIMARY KEY (candidate_id, job_id)
        );
        """
    )


def save_score(s: ScoreOutput):
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO score_results VALUES (?,?,?) ON CONFLICT(candidate_id, job_id) "
            "DO UPDATE SET score_json = excluded.score_json",
            (s.candidate_id, s.job_id, s.model_dump_json()),
        )
    finally:
        conn.close()


def _job_or_404(job_id: str):
    if job_id not in jobs.JOBS:
        raise HTTPException(404, "unknown job")


@router.get("/jobs")
def get_jobs(user: UserOut = Depends(RM)):
    return [
        {k: j[k] for k in ("job_id", "title", "open_since", "target_days", "daily_vacancy_cost_tnd")}
        for j in jobs.list_jobs()
    ]


@router.get("/jobs/{job_id}/rubric", response_model=Rubric)
def get_rubric(job_id: str, user: UserOut = Depends(RM)):
    _job_or_404(job_id)
    return jobs.get_rubric(job_id)


COMPONENTS = {"skills", "experience", "degree", "languages"}
MAX_SKILLS = 60
MAX_WEIGHT = 1000.0


def _rubric_problem(rubric: Rubric) -> str | None:
    """Server-side rubric rules. JSON accepts NaN/Infinity, and NaN < 0 is False, so finiteness is checked
    explicitly: a NaN weight would otherwise reach the scorer and fail every later rescore."""
    weights = [*rubric.skill_weights.values(), *rubric.component_weights.values(), rubric.min_years]
    if not all(math.isfinite(w) for w in weights):
        return "weights and min_years must be finite numbers"
    if any(w < 0 or w > MAX_WEIGHT for w in weights):
        return f"weights must be between 0 and {MAX_WEIGHT:g}"
    if set(rubric.component_weights) - COMPONENTS:
        return f"unknown score components: {sorted(set(rubric.component_weights) - COMPONENTS)}"
    if sum(rubric.component_weights.get(c, 0) for c in COMPONENTS) <= 0:
        return "component weights must not all be zero"
    if not rubric.skill_weights or len(rubric.skill_weights) > MAX_SKILLS:
        return f"a rubric needs 1 to {MAX_SKILLS} skills"
    from ..pipeline.esco import esco_ids  # the validator only ever produces ESCO ids
    unknown = sorted(set(rubric.skill_weights) - set(esco_ids()))
    if unknown:
        return f"unknown skills (not in the ESCO subset): {unknown[:5]}"
    if rubric.min_years > 60:
        return "min_years must be at most 60"
    if len({l.iso for l in rubric.languages}) != len(rubric.languages):
        return "each language may appear once"
    return None


@router.put("/jobs/{job_id}/rubric", response_model=Rubric)
def put_rubric(job_id: str, rubric: Rubric, user: UserOut = Depends(M)):
    _job_or_404(job_id)
    if rubric.job_id != job_id:
        raise HTTPException(400, "job_id mismatch")
    if problem := _rubric_problem(rubric):
        raise HTTPException(400, problem)  # 400 for every rubric rule (frozen contract)
    jobs.put_rubric(rubric, user.id)
    _audit(user.id, "rubric.update", "job", job_id, {"rubric": json.loads(rubric.model_dump_json())})
    return rubric


@router.post("/jobs/{job_id}/rescore", response_model=list[ScoreOutput])
def rescore(job_id: str, user: UserOut = Depends(RM)):
    _job_or_404(job_id)
    validated = _validated(job_id)
    rubric = jobs.get_rubric(job_id)
    out = [score(v, rubric) for v in validated]
    for s in out:
        save_score(s)
    _audit(user.id, "scores.rescore", "job", job_id, {"candidates": len(out)})
    return sorted(out, key=lambda s: -s.total)


@router.get("/jobs/{job_id}/stability")
def get_stability(job_id: str, k: int = Query(5, ge=1, le=50), jitter: float = Query(0.15, ge=0.0, le=0.5),
                  user: UserOut = Depends(RM)):
    """Probability of staying in the top k when every rubric weight moves by up to +/- jitter."""
    _job_or_404(job_id)
    return {"job_id": job_id, "k": k, "jitter": jitter, "draws": DEFAULT_DRAWS,
            "candidates": stability(_validated(job_id), jobs.get_rubric(job_id), k, jitter=jitter)}


@router.get("/jobs/{job_id}/team-gaps")
def get_team_gaps(job_id: str, user: UserOut = Depends(RM)):
    """Proposed rubric from the team's skill gaps. Applying it is a normal, audited PUT /rubric by HR."""
    _job_or_404(job_id)
    out = team_gaps(job_id, jobs.get_rubric(job_id), _validated(job_id))
    if out is None:
        raise HTTPException(404, "no team roster for this job")
    return out


# ---------------------------------------------------------------- fast-track: offer fit, offers, talent pool

CID_RX = re.compile(r"^CAND-[A-Z0-9-]{3,32}$")


def _cid(candidate_id: str) -> str:
    if not CID_RX.match(candidate_id):
        raise HTTPException(404, "candidate not found")
    return candidate_id


def _ranked(job_id: str) -> list[str]:
    rubric = jobs.get_rubric(job_id)
    totals = {v.candidate_id: score(v, rubric).total for v in _validated(job_id)}
    return sorted(totals, key=lambda c: (-totals[c], c))


@router.get("/jobs/{job_id}/offer-fit")
def get_offer_fit(job_id: str, k: int = Query(5, ge=1, le=50), user: UserOut = Depends(RM)):
    """Declared conditions vs. the job's published terms. Shown beside the ranking, never inside it."""
    _job_or_404(job_id)
    out = offer_fit.job_view(job_id, _ranked(job_id), k, date.today())
    if out is None:
        raise HTTPException(404, "no published terms for this job")
    return out


@router.put("/candidates/{candidate_id}/conditions")
def put_conditions(candidate_id: str, body: offer_fit.Conditions, user: UserOut = Depends(RM)):
    """A recruiter records what the candidate said on a call. Typed fields only; audited."""
    conn = connect()
    try:
        found = conn.execute("SELECT 1 FROM candidates WHERE candidate_id = ?", (_cid(candidate_id),)).fetchone()
    finally:
        conn.close()
    if not found:
        raise HTTPException(404, "candidate not found")
    offer_fit.save_conditions(candidate_id, body, "recruiter_call", user.id)
    return body


class OfferIn(BaseModel, extra="forbid"):
    monthly_salary_tnd: int = Field(ge=300, le=50000)
    start_date: date
    lang: Literal["fr", "en", "ar"] = "fr"


@router.post("/candidates/{candidate_id}/offer", response_model=ApprovalItem)
def post_offer(candidate_id: str, body: OfferIn, user: UserOut = Depends(M)):
    try:
        return offer_fit.draft_offer(_cid(candidate_id), body.monthly_salary_tnd, body.start_date, body.lang, user.id)
    except LookupError:
        raise HTTPException(404, "candidate not found")
    except offer_fit.OfferError as e:
        raise HTTPException(422, str(e))


@router.get("/jobs/{job_id}/rediscover")
def get_rediscover(job_id: str, user: UserOut = Depends(RM)):
    """Consented, unexpired talent-pool members re-scored against this job's rubric."""
    _job_or_404(job_id)
    return {"job_id": job_id, "pool_days": rediscover.POOL_DAYS, "candidates": rediscover.rediscover(job_id)}


class InviteIn(BaseModel):
    candidate_ids: conlist(str, min_length=1, max_length=20)


@router.post("/jobs/{job_id}/rediscover/invite", response_model=list[ApprovalItem])
def post_invite(job_id: str, body: InviteIn, user: UserOut = Depends(RM)):
    _job_or_404(job_id)
    return rediscover.invite(job_id, body.candidate_ids, user.id)


@router.delete("/talent-pool/{candidate_id}")
def delete_from_pool(candidate_id: str, user: UserOut = Depends(RM)):
    """The candidate asked to leave the pool. Audited; they are never rediscovered again."""
    if not rediscover.withdraw(_cid(candidate_id), user.id):
        raise HTTPException(404, "not in the talent pool")
    return {"candidate_id": candidate_id, "withdrawn": True}


class ShortlistIn(BaseModel):
    candidate_ids: conlist(str, min_length=1, max_length=50)


@router.post("/jobs/{job_id}/shortlist")
def shortlist(job_id: str, body: ShortlistIn, user: UserOut = Depends(RM)):
    _job_or_404(job_id)
    conn = connect()
    try:
        rows = conn.execute(
            f"SELECT candidate_id, score_json FROM score_results WHERE job_id = ? "
            f"AND candidate_id IN ({','.join('?' * len(body.candidate_ids))})",
            (job_id, *body.candidate_ids),
        ).fetchall()
    finally:
        conn.close()
    scores = {r["candidate_id"]: json.loads(r["score_json"])["total"] for r in rows}
    missing = [c for c in body.candidate_ids if c not in scores]
    if missing:
        raise HTTPException(400, f"no score for candidates: {missing}")
    try:
        from ..workflow.approvals import create_item  # P3
    except ImportError:
        raise HTTPException(501, "workflow.approvals not available yet")
    return create_item(
        kind=ApprovalKind.shortlist_commit,
        title=f"Commit shortlist of {len(scores)} for {job_id}",
        payload={"job_id": job_id, "candidate_ids": body.candidate_ids, "scores": scores},
        created_by=user.id,
        diff={"before": {"status": "proposed"}, "after": {"status": "committed", "candidate_ids": body.candidate_ids}},
    )


class StatusIn(BaseModel):
    status_to: Literal["shortlisted", "interview", "offer", "hired", "rejected", "withdrawn"]


def _hiring_status(conn, candidate_id: str) -> str:
    """Latest executed status change (P3's table); 'applied' before any."""
    try:
        r = conn.execute("SELECT status_to FROM workflow_status_changes WHERE object_type='candidate' "
                         "AND object_id=? ORDER BY at DESC LIMIT 1", (candidate_id,)).fetchone()
    except sqlite3.OperationalError:
        return "applied"
    return r["status_to"] if r else "applied"


@router.post("/jobs/{job_id}/candidates/{candidate_id}/status")
def change_status(job_id: str, candidate_id: str, body: StatusIn, user: UserOut = Depends(RM)):
    """Proposes a hiring status change; nothing changes until a human approves it (P3 handoff H4)."""
    _job_or_404(job_id)
    conn = connect()
    try:
        try:
            found = conn.execute("SELECT 1 FROM candidates WHERE candidate_id=? AND job_id=?",
                                 (candidate_id, job_id)).fetchone()
        except sqlite3.OperationalError:
            found = None
        if not found:
            raise HTTPException(404, "unknown candidate for this job")
        status_from = _hiring_status(conn, candidate_id)
    finally:
        conn.close()
    if status_from == body.status_to:
        raise HTTPException(409, f"candidate is already {status_from}")
    try:
        from ..workflow.approvals import create_item  # P3
    except ImportError:
        raise HTTPException(501, "workflow.approvals not available yet")
    return create_item(
        kind=ApprovalKind.status_change,
        title=f"{candidate_id}: {status_from} -> {body.status_to} ({job_id})",
        payload={"object_type": "candidate", "object_id": candidate_id, "job_id": job_id,
                 "status_from": status_from, "status_to": body.status_to},
        created_by=user.id,
        diff={"before": {"status": status_from}, "after": {"status": body.status_to}},
    )


@router.get("/money")
def get_money(user: UserOut = Depends(MA)):
    return money.dashboard()


class MoneySettingsIn(BaseModel):
    hourly_cost_tnd: float = Field(gt=0, le=1000)


@router.put("/money/settings")
def put_money_settings(body: MoneySettingsIn, user: UserOut = Depends(M)):
    money.set_hourly_cost(body.hourly_cost_tnd)
    _audit(user.id, "money.settings", "settings", "hourly_cost_tnd", {"value": body.hourly_cost_tnd})
    return {"hourly_cost_tnd": body.hourly_cost_tnd}


EVAL_LIMITATIONS = [
    "All CVs, emails and attacks are synthetic and fictional; results describe this corpus, not real applicants.",
    "Intervals are exact 95% Clopper-Pearson bounds; with small samples they are wide, so read the interval, not the point.",
    "A section run without model calls (mode code_path) tests deterministic code (sanitizer, validator, scorer), "
    "not the language model.",
    "A section run with --limit measured a subset of the corpus.",
]


def _rates(obj) -> list[dict]:
    """Every rate block ({k, n, ci95, ...}) inside a section, at any depth."""
    if isinstance(obj, dict):
        found = [obj] if {"k", "n", "ci95"} <= set(obj) else []
        return found + [r for v in obj.values() for r in _rates(v)]
    if isinstance(obj, list):
        return [r for v in obj for r in _rates(v)]
    return []


def eval_report(summary: dict) -> dict:
    """What was measured, how, on how many samples, and what it does not prove (persons/rayen.md)."""
    sections = {}
    for name, sec in (summary.get("sections") or {}).items():
        if not isinstance(sec, dict) or "skipped" in sec:
            sections[name] = {"measured": False, "reason": (sec or {}).get("skipped", "no result")}
            continue
        calls = sec.get("llm_calls_total")
        sizes = [r["n"] for r in _rates(sec) if isinstance(r.get("n"), int)]
        sizes += [v for k, v in sec.items() if k.startswith("n_") and isinstance(v, int)]
        sections[name] = {"measured": True,
                          "mode": "model" if calls else "code_path" if calls == 0 else "unknown",
                          "samples": max(sizes) if sizes else None, "limit": sec.get("limit"),
                          "llm_calls": calls, "seconds": sec.get("seconds")}
    limitations = list(EVAL_LIMITATIONS)
    if summary.get("groq_fallback"):
        limitations.append("Groq fallback was on: some answers may come from a hosted model, not the local one.")
    return {"model": summary.get("model"), "generated_at": summary.get("generated_at"),
            "sections": sections, "limitations": limitations}


@router.get("/eval/summary")
def eval_summary(user: UserOut = Depends(MA)):
    """The harness output as written, plus `report`: an explicit statement of mode, sample size and limits."""
    if not EVAL_SUMMARY.exists():
        return {"status": "not_run"}
    try:
        summary = json.loads(EVAL_SUMMARY.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:  # a broken results file is an error, not an empty success
        raise HTTPException(500, f"eval/results/summary.json is unreadable: {e}")
    return summary | {"report": eval_report(summary)}


@router.get("/eval/fairness")
def eval_fairness(user: UserOut = Depends(MA)):
    if not EVAL_FAIRNESS.exists():
        return {"status": "not_run"}
    return json.loads(EVAL_FAIRNESS.read_text(encoding="utf-8"))


def _audit(actor, action, object_type, object_id, details):
    audit_append(actor, action, object_type, object_id, details)  # never skipped: a failure fails the request
