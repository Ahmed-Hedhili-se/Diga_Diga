"""Pipeline endpoints (P1). Paths frozen in contracts/API.md."""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..config import MAX_UPLOAD_BYTES, UPLOAD_DIR
from ..contracts import Role, UserOut
from ..auth.core import require_roles
from . import answer_desk, service

router = APIRouter()

RM = require_roles(Role.recruiter, Role.hr_manager)
MA = require_roles(Role.hr_manager, Role.admin)
EM = require_roles(Role.employee, Role.hr_manager)

CID_RX = re.compile(r"^CAND-[A-Z0-9-]{3,32}$")


def _cid(candidate_id: str) -> str:
    if not CID_RX.match(candidate_id):
        raise HTTPException(404, "candidate not found")
    return candidate_id


def _conditions(salary_min, salary_max, notice_weeks, work_modes, commitments_ok):
    """Optional fast-track fields from the application form: typed and range-checked, never read from the CV."""
    if salary_min is None:
        return None
    from pydantic import ValidationError

    from ..scoring.offer_fit import Conditions  # P2
    split = lambda s: [x.strip() for x in (s or "").split(",") if x.strip()]
    try:
        return Conditions(salary_min=salary_min, salary_max=salary_max, notice_weeks=notice_weeks or 0,
                          work_modes=split(work_modes), commitments_ok=split(commitments_ok))
    except ValidationError as e:
        raise HTTPException(422, f"invalid conditions: {e.errors()[0]['msg']}")


@router.post("/candidates")
def upload_candidate(
    file: UploadFile = File(...),
    job_id: str = Form(...),
    name: str = Form(...),
    email: str = Form(...),
    talent_pool_consent: bool = Form(False),
    salary_min: int | None = Form(None),
    salary_max: int | None = Form(None),
    notice_weeks: int | None = Form(None),
    work_modes: str | None = Form(None, max_length=40),
    commitments_ok: str | None = Form(None, max_length=40),
    user: UserOut = Depends(RM),
):
    cond = _conditions(salary_min, salary_max, notice_weeks, work_modes, commitments_ok)
    data = file.file.read(MAX_UPLOAD_BYTES + 1)  # never read more than the limit
    try:
        out = service.process_cv(data, name.strip(), email.strip(), job_id.strip(), actor=user.id)
    except service.UploadRejected as e:
        raise HTTPException(422, str(e))
    if cond is not None:
        from ..scoring.offer_fit import save_conditions
        save_conditions(out["candidate_id"], cond, "candidate_form", user.id)
    if talent_pool_consent:
        from ..scoring.rediscover import add
        add(out["candidate_id"], job_id.strip(), user.id)
    return out


@router.get("/candidates")
def list_candidates(job_id: str | None = None, user: UserOut = Depends(RM)):
    return service.list_candidates(job_id)


@router.get("/candidates/{candidate_id}")
def get_candidate(candidate_id: str, user: UserOut = Depends(RM)):
    c = service.get_candidate(_cid(candidate_id))
    if not c:
        raise HTTPException(404, "candidate not found")
    return c


@router.get("/candidates/{candidate_id}/text")
def get_candidate_text(candidate_id: str, user: UserOut = Depends(RM)):
    t = service.get_text(_cid(candidate_id))
    if not t:
        raise HTTPException(404, "candidate not found")
    return t


@router.get("/candidates/{candidate_id}/pdf")
def get_candidate_pdf(candidate_id: str, user: UserOut = Depends(RM)):
    p = service.get_pdf_path(_cid(candidate_id))
    if not p:
        raise HTTPException(404, "candidate not found")
    path = Path(p).resolve()
    if path.parent != UPLOAD_DIR.resolve() or not path.is_file():
        raise HTTPException(404, "file missing")
    return FileResponse(path, media_type="application/pdf", filename=f"{candidate_id}.pdf",
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
                        content_disposition_type="attachment")


@router.get("/security/findings")
def security_findings(user: UserOut = Depends(MA)):
    return service.security_findings()


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=answer_desk.MAX_QUESTION_CHARS)


@router.post("/answer-desk/ask")
def ask_answer_desk(body: AskIn, user: UserOut = Depends(EM)):
    """{kind:"extract", extracts:[{text, section, section_id, page}]} | {kind:"routed", ticket_id, topic}
    | {kind:"ask_hr", message}. Handbook text word for word; nothing is generated."""
    out = answer_desk.answer(user, body.question)
    from ..team.knowledge_gaps import record_answer  # HR Nexus radar: section + week only, never the text
    record_answer(out, body.question)
    return out
