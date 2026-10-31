"""Scoring, eval and money endpoints (P2). Paths frozen in contracts/API.md."""
from __future__ import annotations

import json
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, conlist

from ..config import ROOT
from ..contracts import ApprovalKind, Role, Rubric, ScoreOutput, UserOut
from ..auth.core import require_roles
from ..db import connect, register_schema
from . import jobs, money
from .scorer import score

router = APIRouter()

RM = require_roles(Role.recruiter, Role.hr_manager)
M = require_roles(Role.hr_manager)
MA = require_roles(Role.hr_manager, Role.admin)

EVAL_SUMMARY = ROOT / "eval" / "results" / "summary.json"


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


@router.put("/jobs/{job_id}/rubric", response_model=Rubric)
def put_rubric(job_id: str, rubric: Rubric, user: UserOut = Depends(M)):
    _job_or_404(job_id)
    if rubric.job_id != job_id:
        raise HTTPException(400, "job_id mismatch")
    if any(w < 0 for w in rubric.skill_weights.values()) or any(w < 0 for w in rubric.component_weights.values()):
        raise HTTPException(400, "weights must be >= 0")
    jobs.put_rubric(rubric, user.id)
    _audit(user.id, "rubric.update", "job", job_id, {"rubric": json.loads(rubric.model_dump_json())})
    return rubric


@router.post("/jobs/{job_id}/rescore", response_model=list[ScoreOutput])
def rescore(job_id: str, user: UserOut = Depends(RM)):
    _job_or_404(job_id)
    try:
        from ..pipeline import service  # P1
        validated = service.list_validated(job_id)
    except (ImportError, AttributeError):
        raise HTTPException(501, "pipeline.service.list_validated not available yet")
    rubric = jobs.get_rubric(job_id)
    out = [score(v, rubric) for v in validated]
    for s in out:
        save_score(s)
    return sorted(out, key=lambda s: -s.total)


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


@router.get("/eval/summary")
def eval_summary(user: UserOut = Depends(MA)):
    if not EVAL_SUMMARY.exists():
        return {"status": "not_run"}
    return json.loads(EVAL_SUMMARY.read_text(encoding="utf-8"))


def _audit(actor, action, object_type, object_id, details):
    try:
        from ..workflow.audit import append  # P3
    except ImportError:
        return
    append(actor, action, object_type, object_id, details)
