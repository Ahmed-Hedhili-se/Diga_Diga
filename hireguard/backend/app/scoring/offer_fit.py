"""Offer-fit check (fast-track): can we offer what the candidate declared they need?

Not a prediction and never part of the score. Candidates (or a recruiter after a phone screen) declare a
salary range, notice period, acceptable work modes and commitments in typed, range-checked fields; code
compares them with the job's published terms (data/offer/terms.json). Nothing is read from the CV text or
the model. HR sees deal-breakers before spending interview time on them.

Why not "probability to accept": the strongest predictors of acceptance are current pay (the EU Pay
Transparency Directive 2023/970, Art. 5, forbids asking for it), commute distance (a proxy for region)
and family situation (a proxy for gender). Ranking on them would demote people for reasons that are not
job-related. Declared conditions are the candidate's own words, shown beside the ranking, never inside it.

  fit         nothing to negotiate
  negotiable  declared minimum up to 10% above the band, or available up to 4 weeks after start_by
  mismatch    beyond that, or a work mode / commitment the candidate declined
  unknown     nothing declared yet: ask, don't guess
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, conint, model_validator

from ..config import DATA_DIR
from ..contracts import ApprovalKind
from ..db import connect, register_schema, tx

TERMS_PATH = DATA_DIR / "offer" / "terms.json"
SALARY_SLACK = 0.10
START_SLACK = timedelta(weeks=4)
ORDER = {"fit": 0, "unknown": 1, "negotiable": 2, "mismatch": 3}

WorkMode = Literal["onsite", "hybrid", "remote"]
Commitment = Literal["on_call", "travel", "shift_work"]


class OfferTerms(BaseModel, extra="forbid"):
    job_id: str
    pay_band_tnd_month: tuple[int, int]
    work_mode: WorkMode
    location: str
    start_by: date
    contract: str
    commitments: list[Commitment] = []


class Conditions(BaseModel, extra="forbid"):
    """Declared by the candidate (or noted by a recruiter on a call). Gross TND per month."""
    salary_min: conint(ge=300, le=50000)
    salary_max: conint(ge=300, le=50000) | None = None
    notice_weeks: conint(ge=0, le=26) = 0
    work_modes: list[WorkMode] = Field(min_length=1, max_length=3)
    commitments_ok: list[Commitment] = []

    @model_validator(mode="after")
    def _range(self):
        if self.salary_max is not None and self.salary_max < self.salary_min:
            raise ValueError("salary_max must be >= salary_min")
        self.work_modes = sorted(set(self.work_modes))
        self.commitments_ok = sorted(set(self.commitments_ok))
        return self


@register_schema
def _schema(conn: sqlite3.Connection):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS candidate_conditions (
            candidate_id TEXT PRIMARY KEY,
            conditions TEXT NOT NULL,
            source TEXT NOT NULL,            -- candidate_form | recruiter_call | seed
            declared_by TEXT NOT NULL,
            declared_at TEXT NOT NULL
        );
        """
    )


@lru_cache(maxsize=1)
def _all_terms() -> dict[str, OfferTerms]:
    raw = json.loads(TERMS_PATH.read_text(encoding="utf-8"))["jobs"]
    return {job_id: OfferTerms(job_id=job_id, **t) for job_id, t in raw.items()}


def get_terms(job_id: str) -> OfferTerms | None:
    return _all_terms().get(job_id)

# ---------------------------------------------------------------- the check (pure)


def _salary(t: OfferTerms, c: Conditions) -> dict:
    lo, hi = t.pay_band_tnd_month
    detail = f"expects from {c.salary_min} TND; band {lo}-{hi} TND"
    if c.salary_min <= hi:
        return {"check": "salary", "status": "fit", "detail": detail}
    if c.salary_min <= hi * (1 + SALARY_SLACK):
        return {"check": "salary", "status": "negotiable", "detail": f"{detail} ({c.salary_min / hi - 1:.0%} above)"}
    return {"check": "salary", "status": "mismatch", "detail": f"{detail} ({c.salary_min / hi - 1:.0%} above)"}


def _start(t: OfferTerms, c: Conditions, today: date) -> dict:
    earliest = today + timedelta(weeks=c.notice_weeks)
    detail = f"available from {earliest.isoformat()}; role starts by {t.start_by.isoformat()}"
    if earliest <= t.start_by:
        return {"check": "start_date", "status": "fit", "detail": detail}
    return {"check": "start_date", "status": "negotiable" if earliest <= t.start_by + START_SLACK else "mismatch",
            "detail": detail}


def _mode(t: OfferTerms, c: Conditions) -> dict:
    ok = t.work_mode in c.work_modes
    return {"check": "work_mode", "status": "fit" if ok else "mismatch",
            "detail": f"role is {t.work_mode}; accepts {', '.join(c.work_modes)}"}


def _commitments(t: OfferTerms, c: Conditions) -> dict:
    declined = [x for x in t.commitments if x not in c.commitments_ok]
    if not t.commitments:
        return {"check": "commitments", "status": "fit", "detail": "none required"}
    return {"check": "commitments", "status": "mismatch" if declined else "fit",
            "detail": f"declined: {', '.join(declined)}" if declined else f"accepts {', '.join(t.commitments)}"}


def offer_fit(terms: OfferTerms, cond: Conditions | None, today: date) -> dict:
    if cond is None:
        return {"status": "unknown", "checks": []}
    checks = [_salary(terms, cond), _start(terms, cond, today), _mode(terms, cond), _commitments(terms, cond)]
    return {"status": max((c["status"] for c in checks), key=ORDER.__getitem__), "checks": checks}


def band_coverage(terms: OfferTerms, top_k: list[str], conds: dict[str, Conditions]) -> dict:
    """Job-level, not per person: how many of the top k declared a minimum the band can pay."""
    declared = [c for c in top_k if c in conds]
    within = [c for c in declared if conds[c].salary_min <= terms.pay_band_tnd_month[1]]
    return {"k": len(top_k), "declared": len(declared), "within_band": len(within),
            "share": round(len(within) / len(declared), 3) if declared else None,
            "band": list(terms.pay_band_tnd_month)}

# ---------------------------------------------------------------- storage


def save_conditions(candidate_id: str, cond: Conditions, source: str, actor: str,
                    conn: sqlite3.Connection | None = None):
    if conn is None:
        with tx() as c:
            return save_conditions(candidate_id, cond, source, actor, conn=c)
    from ..workflow import audit  # P3
    from ..workflow.common import now_iso
    data = cond.model_dump_json()
    conn.execute("INSERT INTO candidate_conditions VALUES (?,?,?,?,?) ON CONFLICT(candidate_id) DO UPDATE SET "
                 "conditions = excluded.conditions, source = excluded.source, declared_by = excluded.declared_by, "
                 "declared_at = excluded.declared_at", (candidate_id, data, source, actor, now_iso()))
    audit.append(actor, "conditions.update", "candidate", candidate_id,
                 {"source": source, "conditions": json.loads(data)}, conn=conn)


def get_conditions(candidate_ids: list[str]) -> dict[str, Conditions]:
    if not candidate_ids:
        return {}
    conn = connect()
    try:
        rows = conn.execute(f"SELECT candidate_id, conditions FROM candidate_conditions WHERE candidate_id IN "
                            f"({','.join('?' * len(candidate_ids))})", tuple(candidate_ids)).fetchall()
    finally:
        conn.close()
    return {r["candidate_id"]: Conditions.model_validate_json(r["conditions"]) for r in rows}


def job_view(job_id: str, ranked: list[str], k: int, today: date) -> dict | None:
    terms = get_terms(job_id)
    if terms is None:
        return None
    conds = get_conditions(ranked)
    return {"job_id": job_id, "terms": json.loads(terms.model_dump_json()),
            "band_coverage": band_coverage(terms, ranked[:k], conds),
            "candidates": {c: offer_fit(terms, conds.get(c), today) for c in ranked}}

# ---------------------------------------------------------------- offer letter draft


WORK_MODE_LABEL = {
    "fr": {"onsite": "sur site", "hybrid": "hybride", "remote": "à distance"},
    "en": {"onsite": "on site", "hybrid": "hybrid", "remote": "remote"},
    "ar": {"onsite": "حضوري", "hybrid": "هجين", "remote": "عن بعد"},
}


class OfferError(ValueError):
    pass


def draft_offer(candidate_id: str, monthly_salary_tnd: int, start_date: date, lang: str, actor: str,
                today: date | None = None):
    """An offer letter from typed fields into the approval queue (2 HR managers, never the author).

    The salary is chosen by HR inside the published band, not copied from what the candidate asked:
    pay follows the role, so a lower ask never becomes a lower offer (Directive 2023/970).
    """
    from ..workflow import approvals, templates
    from ..workflow.drafting import COMPANY, RECRUITER, job_title

    today = today or date.today()
    with tx() as conn:
        c = conn.execute("SELECT candidate_id, name, email, job_id FROM candidates WHERE candidate_id = ?",
                         (candidate_id,)).fetchone()
        if not c:
            raise LookupError("candidate not found")
        terms = get_terms(c["job_id"])
        if terms is None:
            raise OfferError("no published terms for this job")
        lo, hi = terms.pay_band_tnd_month
        if not lo <= monthly_salary_tnd <= hi:
            raise OfferError(f"salary must be inside the published band {lo}-{hi} TND")
        if not today <= start_date <= today + timedelta(days=365):
            raise OfferError("start date must be within the next 12 months")
        if conn.execute("SELECT 1 FROM approval_items WHERE kind = 'offer' AND is_canary = 0 "
                        "AND status IN ('pending', 'approved') AND json_extract(payload, '$.candidate_id') = ?",
                        (candidate_id,)).fetchone():
            raise OfferError("an offer for this candidate is already waiting for approval")
        lang = lang if lang in WORK_MODE_LABEL else "fr"
        subject, body = templates.render("email", "offer_letter", lang, {
            "candidate_name": c["name"], "job_title": job_title(conn, c["job_id"]), "contract": terms.contract,
            "monthly_salary_tnd": monthly_salary_tnd, "start_date": start_date.isoformat(),
            "work_mode": WORK_MODE_LABEL[lang][terms.work_mode], "location": terms.location,
            "recruiter_name": RECRUITER["name"], "company_name": COMPANY})
        offer = {"monthly_salary_tnd": monthly_salary_tnd, "start_date": start_date.isoformat()}
        return approvals.create_item(
            ApprovalKind.offer, f"Offer to {candidate_id} for {c['job_id']}: {monthly_salary_tnd} TND",
            {"to": c["email"], "candidate_id": candidate_id, "job_id": c["job_id"], "recipient_verified": True,
             "offer": offer, "email": {"to": c["email"], "subject": subject, "body": body, "lang": lang}},
            actor, diff={"before": None, "after": {"to": c["email"], **offer}}, conn=conn)

# ---------------------------------------------------------------- demo seed (fictional)


DEMO_CONDITIONS = {
    "CAND-001": dict(salary_min=3200, salary_max=3600, notice_weeks=4, work_modes=["hybrid", "onsite"],
                     commitments_ok=["on_call"]),
    "CAND-002": dict(salary_min=4600, salary_max=5200, notice_weeks=8, work_modes=["hybrid", "remote"],
                     commitments_ok=["on_call"]),                       # far above the band: mismatch
    "CAND-003": dict(salary_min=2900, notice_weeks=12, work_modes=["hybrid"], commitments_ok=["on_call"]),
    "CAND-004": dict(salary_min=3000, salary_max=3400, notice_weeks=4, work_modes=["remote"]),  # remote, no on-call
    "CAND-005": dict(salary_min=4000, notice_weeks=2, work_modes=["hybrid", "onsite"],
                     commitments_ok=["on_call"]),                       # 5% above: negotiable
    "CAND-006": dict(salary_min=2800, notice_weeks=0, work_modes=["onsite", "hybrid"], commitments_ok=["on_call"]),
    "CAND-008": dict(salary_min=3300, salary_max=3800, notice_weeks=4, work_modes=["hybrid"],
                     commitments_ok=["on_call"]),
    # CAND-007 has not declared anything yet: "unknown", ask on the first call
}


def seed_conditions():
    conn = connect()
    try:
        have = {r["candidate_id"] for r in conn.execute("SELECT candidate_id FROM candidates")}
    finally:
        conn.close()
    for cid, c in DEMO_CONDITIONS.items():
        if cid in have:
            save_conditions(cid, Conditions(**c), "seed", "system:seed")
