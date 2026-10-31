"""Talent-pool rediscovery (fast-track): a shortlist on day 1 from people who already applied and opted in.

Instead of an agent that hunts profiles on the web (real personal data, no consent, and optimised
targeting is known to skew by gender and race: Ali et al., CSCW 2019), we re-read our own consented
pool. Past applicants who ticked the talent-pool box are re-scored against a new job with the same
deterministic rubric as everyone else. Consent expires after POOL_DAYS (CNIL guidance: 2 years after
the last contact) and can be withdrawn at any time; expired or withdrawn people are never shown.

The output is a list for a recruiter. Contacting someone is an email draft in the approval queue.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone

from ..config import DATA_DIR, ROOT
from ..contracts import ApprovalItem, ApprovalKind, ValidatedCV
from ..db import connect, register_schema, tx
from . import jobs
from .scorer import score

POOL_DAYS = 730


@register_schema
def _schema(conn: sqlite3.Connection):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS talent_pool (
            candidate_id TEXT PRIMARY KEY,
            source_job_id TEXT NOT NULL,
            consent_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            withdrawn_at TEXT
        );
        """
    )


def add(candidate_id: str, source_job_id: str, actor: str, consent_at: datetime | None = None,
        conn: sqlite3.Connection | None = None):
    """Called only when the candidate ticked the opt-in box on the application form."""
    if conn is None:
        with tx() as c:
            return add(candidate_id, source_job_id, actor, consent_at, conn=c)
    from ..workflow import audit  # P3
    at = consent_at or datetime.now(timezone.utc)
    expires = at + timedelta(days=POOL_DAYS)
    conn.execute("INSERT INTO talent_pool VALUES (?,?,?,?,NULL) ON CONFLICT(candidate_id) DO UPDATE SET "
                 "source_job_id = excluded.source_job_id, consent_at = excluded.consent_at, "
                 "expires_at = excluded.expires_at, withdrawn_at = NULL",
                 (candidate_id, source_job_id, at.isoformat(), expires.isoformat()))
    audit.append(actor, "talent_pool.consent", "candidate", candidate_id,
                 {"source_job_id": source_job_id, "expires_at": expires.isoformat()}, conn=conn)


def withdraw(candidate_id: str, actor: str) -> bool:
    from ..workflow import audit
    from ..workflow.common import now_iso
    with tx() as conn:
        cur = conn.execute("UPDATE talent_pool SET withdrawn_at = ? WHERE candidate_id = ? AND withdrawn_at IS NULL",
                           (now_iso(), candidate_id))
        if cur.rowcount:
            audit.append(actor, "talent_pool.withdraw", "candidate", candidate_id, {}, conn=conn)
        return bool(cur.rowcount)


def rediscover(job_id: str, today: date | None = None) -> list[dict]:
    today = today or date.today()
    rubric = jobs.get_rubric(job_id)
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT p.candidate_id, p.source_job_id, p.expires_at, c.name, c.email, d.validated "
            "FROM talent_pool p JOIN candidates c ON c.candidate_id = p.candidate_id "
            "JOIN pipeline_docs d ON d.doc_id = c.doc_id "
            "WHERE p.withdrawn_at IS NULL AND p.expires_at > ? AND c.job_id != ? "
            "AND lower(c.email) NOT IN (SELECT lower(email) FROM candidates WHERE job_id = ?)",
            (today.isoformat(), job_id, job_id)).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        v = ValidatedCV.model_validate_json(r["validated"])
        s = score(v, rubric)
        out.append({"candidate_id": r["candidate_id"], "name": r["name"], "source_job_id": r["source_job_id"],
                    "total": s.total, "needs_human": s.needs_human, "consent_expires_at": r["expires_at"][:10],
                    "matched_skills": sorted(sk.label for sk in v.skills if sk.esco_id in rubric.skill_weights)})
    return sorted(out, key=lambda x: (-x["total"], x["candidate_id"]))


def _already_invited(conn, candidate_id: str, job_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM approval_items WHERE is_canary = 0 AND status != 'rejected' "
        "AND json_extract(payload, '$.talent_invite') = ? AND json_extract(payload, '$.candidate_id') = ?",
        (job_id, candidate_id)).fetchone() is not None


def invite(job_id: str, candidate_ids: list[str], actor: str, lang: str = "fr") -> list[ApprovalItem]:
    """Drafts an invitation to apply. Only people currently in the consented pool for this job."""
    from ..workflow import approvals, templates
    from ..workflow.drafting import COMPANY, RECRUITER, job_title
    from .offer_fit import get_terms

    eligible = {x["candidate_id"]: x for x in rediscover(job_id)}
    terms = get_terms(job_id)
    out = []
    with tx() as conn:
        for cid in candidate_ids:
            if cid not in eligible or _already_invited(conn, cid, job_id):
                continue
            to = conn.execute("SELECT email FROM candidates WHERE candidate_id = ?", (cid,)).fetchone()["email"]
            subject, body = templates.render("email", "talent_invite", lang, {
                "candidate_name": eligible[cid]["name"], "job_title": job_title(conn, job_id),
                "location": terms.location if terms else "Tunis", "recruiter_name": RECRUITER["name"],
                "company_name": COMPANY})
            out.append(approvals.create_item(
                ApprovalKind.email_send, f"Talent-pool invitation {cid} for {job_id}",
                {"to": to, "subject": subject, "body": body, "lang": lang, "candidate_id": cid,
                 "recipient_verified": True, "talent_invite": job_id},
                actor, diff={"before": None, "after": {"to": to, "subject": subject}}, conn=conn))
    return out

# ---------------------------------------------------------------- demo seed (fictional)


CLOSED_JOB = "JOB-DATA-00"  # a fictional 2025 data role, closed: its applicants are the demo pool
N_POOL = 20


def seed_pool():
    """20 fictional past applicants, rendered and run through the real pipeline (ground-truth extraction).
    P001-P014 consented, P015-P017 consent expired, P018-P020 never opted in."""
    eval_dir = ROOT / "eval"
    if str(eval_dir) not in sys.path:
        sys.path.insert(0, str(eval_dir))
    from gen_cvs import render_text  # noqa: E402  (eval helpers, fictional data only)
    from oracle import gt_extraction
    from render import text_pdf

    from ..pipeline.sanitizer import sanitize
    from ..pipeline.service import process_cv

    gts = [json.loads(p.read_text(encoding="utf-8"))["ground_truth"]
           for p in sorted((DATA_DIR / "cv_ground_truth").glob("CV-*.json"))]
    gts = [g for g in gts if g["job_id"] == "JOB-DATA-01"][:N_POOL]
    for i, gt in enumerate(gts, start=1):
        cid = f"CAND-P{i:03d}"
        pdf = text_pdf(render_text(gt), gt["lang"]).tobytes()
        process_cv(pdf, gt["name"], gt["email"], CLOSED_JOB, candidate_id=cid, actor="system:seed",
                   extraction_override=gt_extraction(gt, sanitize(pdf).visible_text))
        if i <= 14:
            add(cid, CLOSED_JOB, "system:seed", consent_at=datetime(2025, 9, 15, tzinfo=timezone.utc))
        elif i <= 17:
            add(cid, CLOSED_JOB, "system:seed", consent_at=datetime(2024, 6, 1, tzinfo=timezone.utc))
