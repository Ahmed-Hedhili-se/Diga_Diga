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
from . import service

router = APIRouter()

RM = require_roles(Role.recruiter, Role.hr_manager)
MA = require_roles(Role.hr_manager, Role.admin)
EM = require_roles(Role.employee, Role.hr_manager)

CID_RX = re.compile(r"^CAND-[A-Z0-9-]{3,32}$")


def _cid(candidate_id: str) -> str:
    if not CID_RX.match(candidate_id):
        raise HTTPException(404, "candidate not found")
    return candidate_id


@router.post("/candidates")
def upload_candidate(
    file: UploadFile = File(...),
    job_id: str = Form(...),
    name: str = Form(...),
    email: str = Form(...),
    user: UserOut = Depends(RM),
):
    data = file.file.read(MAX_UPLOAD_BYTES + 1)  # never read more than the limit
    try:
        return service.process_cv(data, name.strip(), email.strip(), job_id.strip(), actor=user.id)
    except service.UploadRejected as e:
        raise HTTPException(422, str(e))


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
    question: str = Field(min_length=3, max_length=500)


@router.post("/answer-desk/ask")
def answer_desk(body: AskIn, user: UserOut = Depends(EM)):
    raise HTTPException(501, "Answer Desk retrieval is scheduled after H9")
