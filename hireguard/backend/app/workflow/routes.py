"""P3 endpoints (contracts/API.md, section "Workflow and security")."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel

from ..contracts import ApprovalItem, ApprovalKind, AuditEntry, Role, UserOut
from ..auth.core import require_roles
from . import anchor, approvals, audit, documents, email_gate, executor, followups, interviews, mock_calendar

router = APIRouter()
router.add_event_handler("startup", anchor.start_loop)

R, M, E, A = Role.recruiter, Role.hr_manager, Role.employee, Role.admin
MAX_EML_BYTES = 256 * 1024


class DecisionIn(BaseModel):
    decision: Literal["approve", "reject"]


class BatchDecisionIn(DecisionIn):
    item_ids: list[str]

# ---------------------------------------------------------------- inbox


@router.post("/inbox/ingest")
async def inbox_ingest(request: Request, user: UserOut = Depends(require_roles(A))):
    raw = await request.body()
    if len(raw) > MAX_EML_BYTES:
        raise HTTPException(413, "email too large")
    return email_gate.ingest(raw)


@router.get("/inbox")
def inbox(user: UserOut = Depends(require_roles(R, M))):
    return email_gate.digest()


@router.post("/inbox/{inbox_id}/release-request", response_model=ApprovalItem)
def inbox_release_request(inbox_id: str, user: UserOut = Depends(require_roles(M))):
    item = email_gate.get(inbox_id)
    if item["status"] != "held":
        raise HTTPException(409, "only held emails can be released")
    return approvals.create_item(ApprovalKind.held_email_release, f"Release held email {inbox_id}",
                                 {"inbox_id": inbox_id, "suspicious": True, "reasons": item["reasons"]},
                                 created_by=user.id, diff={"before": {"status": "held"}, "after": {"status": "released"}})

# ---------------------------------------------------------------- approvals + executor


@router.get("/approvals")
def approval_queue(user: UserOut = Depends(require_roles(R, M))):
    return approvals.queue(user)


@router.post("/approvals/{item_id}/decision", response_model=ApprovalItem)
def approval_decide(item_id: str, body: DecisionIn, user: UserOut = Depends(require_roles(R, M))):
    return approvals.decide(item_id, user, body.decision)


@router.post("/approvals/batches/{batch_id}/decision", response_model=list[ApprovalItem])
def approval_decide_batch(batch_id: str, body: BatchDecisionIn, user: UserOut = Depends(require_roles(R, M))):
    return approvals.decide_batch(batch_id, body.item_ids, user, body.decision)


@router.post("/executor/run/{item_id}")
def executor_run(item_id: str, user: UserOut = Depends(require_roles(R, M))):
    return executor.run(item_id, user)


@router.get("/reviewer/stats")
def reviewer_stats(user: UserOut = Depends(require_roles(M, A))):
    return approvals.reviewer_stats()

# ---------------------------------------------------------------- follow-up reminders (drafts only)


@router.get("/followups/preview")
def followups_preview(days: int = Query(3, ge=1, le=60), user: UserOut = Depends(require_roles(R, M))):
    return followups.preview(days)


@router.post("/followups/run")
def followups_run(days: int = Query(3, ge=1, le=60), user: UserOut = Depends(require_roles(R, M))):
    return followups.run(user, days)

# ---------------------------------------------------------------- calendar


@router.get("/calendar/slots")
def calendar_slots(recruiter_id: str = Query("recruiter", max_length=64), user: UserOut = Depends(require_roles(R, M))):
    return mock_calendar.free_slots(recruiter_id, 3)

# ---------------------------------------------------------------- audit


@router.get("/audit", response_model=list[AuditEntry])
def audit_list(limit: int = Query(100, ge=1, le=1000), user: UserOut = Depends(require_roles(M, A))):
    return audit.list_entries(limit)


@router.get("/audit/verify")
def audit_verify(user: UserOut = Depends(require_roles(M, A))):
    return audit.verify()


@router.post("/audit/anchor")
def audit_anchor(user: UserOut = Depends(require_roles(A))):
    return anchor.anchor_now()

# ---------------------------------------------------------------- documents


@router.post("/documents/request", response_model=ApprovalItem)
def documents_request(body: documents.DocumentRequest, user: UserOut = Depends(require_roles(E))):
    try:
        return documents.request_document(user, body)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/documents/mine")
def documents_mine(user: UserOut = Depends(require_roles(E))):
    return documents.list_mine(user)


@router.get("/documents/{doc_id}/download")
def documents_download(doc_id: str, user: UserOut = Depends(require_roles(E, M))):
    pdf, filename = documents.download(doc_id, user)
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
    })

# ---------------------------------------------------------------- interviews (built, not demoed)


@router.post("/interviews/{interview_id}/scorecard")
def interview_scorecard(interview_id: str, card: interviews.Scorecard, user: UserOut = Depends(require_roles(R, M))):
    return interviews.submit_scorecard(interview_id, card, user)


@router.get("/interviews/reminders")
def interview_reminders(user: UserOut = Depends(require_roles(M))):
    return interviews.reminders()
