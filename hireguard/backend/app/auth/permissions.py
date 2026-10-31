"""RBAC: the single source of truth for who may do what (P4).

- `ROLE_PERMISSIONS` is the role -> permission matrix. `/api/auth/me` sends the caller's row to the frontend,
  which renders nav, pages and buttons from it. The backend stays the real guard.
- `ROUTE_PERMISSIONS` names the permission every API route needs. `tests/test_rbac.py` walks FastAPI's route
  table and fails if a route is missing here, unprotected, or guarded by a role set that disagrees with the matrix.
  P4 routes use `require_permission`; other layers still use `require_roles`, and the test keeps both in sync.
- Separation of duties: the Admin manages accounts and the platform but cannot read candidate files, scores or
  inboxes, and cannot decide HR approvals (an IT admin must not read CVs).
- Object-level rules (an employee sees only their own documents and questions, 404 for anything else) are
  enforced in the owning module; the permission only gets the caller through the door.
"""
from enum import Enum

from ..contracts import Role


class Permission(str, Enum):
    # candidates and scoring (P1, P2)
    candidates_read = "candidates.read"
    candidates_upload = "candidates.upload"
    scores_read = "scores.read"                      # jobs, rubrics, scores
    scores_rescore = "scores.rescore"
    shortlist_propose = "shortlist.propose"
    candidates_status_propose = "candidates.status_propose"  # hiring status change -> approval item
    rubric_edit = "rubric.edit"
    # trust analytics (mnasri): offer fit, talent pool, reviewer attention
    offer_conditions_edit = "offers.conditions"     # candidate's offer conditions, used by offer fit
    offer_propose = "offers.propose"                # offer letter -> approval item (2 HR approvers)
    talent_pool_manage = "talent_pool.manage"       # rediscovery invitations (approval items), pool removal
    approvals_attention_read = "approvals.attention"  # canary miss rate by batch size (process-level)
    # approvals and execution (P3)
    approvals_decide = "approvals.decide"            # routine items
    approvals_decide_high_risk = "approvals.decide_high_risk"  # offers, documents, leave, held mail, 2nd approver
    approvals_execute = "approvals.execute"
    # inbox and candidate follow-ups (P3)
    inbox_read = "inbox.read"
    inbox_release_request = "inbox.release_request"
    inbox_ingest = "inbox.ingest"
    followups_manage = "followups.manage"
    # interviews (P3)
    calendar_read = "calendar.read"
    interviews_scorecard = "interviews.scorecard"
    interviews_reminders = "interviews.reminders"
    # employee self-service (P3, P1)
    documents_request = "documents.request"          # request + list own
    documents_read = "documents.read"                # download: own (employee) or any (HR)
    documents_release = "documents.release"          # decided through the approval queue
    questions_ask = "questions.ask"
    questions_read = "questions.read"                # own (employee) or all (HR)
    questions_reply = "questions.reply"
    answer_desk_ask = "answer_desk.ask"
    # oversight
    security_center_read = "security_center.read"    # blocked attacks, evaluation, reviewer vigilance
    audit_read = "audit.read"
    audit_anchor = "audit.anchor"
    money_read = "money.read"
    money_edit = "money.edit"
    # platform administration
    users_manage = "users.manage"
    erp_status = "erp.status"
    erp_import = "erp.import"
    erp_configure = "erp.configure"                  # .env today; reserved for a settings screen


P = Permission

_RECRUITER = {
    P.candidates_read, P.candidates_upload, P.scores_read, P.scores_rescore, P.shortlist_propose,
    P.candidates_status_propose, P.approvals_decide, P.approvals_execute, P.inbox_read, P.followups_manage,
    P.calendar_read, P.interviews_scorecard, P.erp_status, P.erp_import,
    P.offer_conditions_edit, P.talent_pool_manage, P.approvals_attention_read,
}

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.recruiter: frozenset(_RECRUITER),
    Role.hr_manager: frozenset(_RECRUITER | {
        P.rubric_edit, P.approvals_decide_high_risk, P.inbox_release_request, P.interviews_reminders,
        P.documents_read, P.documents_release, P.questions_read, P.questions_reply, P.answer_desk_ask,
        P.security_center_read, P.audit_read, P.money_read, P.money_edit, P.offer_propose,
    }),
    Role.employee: frozenset({
        P.documents_request, P.documents_read, P.questions_ask, P.questions_read, P.answer_desk_ask,
    }),
    Role.admin: frozenset({
        P.security_center_read, P.audit_read, P.audit_anchor, P.money_read,
        P.users_manage, P.inbox_ingest, P.erp_status, P.erp_configure, P.approvals_attention_read,
    }),
}

# Routes open to any signed-in user (their own session) and routes open to everyone.
AUTHENTICATED = "authenticated"
PUBLIC = "public"

ROUTE_PERMISSIONS: dict[tuple[str, str], Permission | str] = {
    # auth (P4)
    ("POST", "/api/auth/login"): PUBLIC,
    ("GET", "/api/health"): PUBLIC,
    ("POST", "/api/auth/logout"): AUTHENTICATED,
    ("POST", "/api/auth/logout-all"): AUTHENTICATED,
    ("GET", "/api/auth/me"): AUTHENTICATED,
    ("GET", "/api/auth/permissions"): AUTHENTICATED,
    ("GET", "/api/auth/users"): P.users_manage,
    ("POST", "/api/auth/users"): P.users_manage,
    ("PATCH", "/api/auth/users/{user_id}"): P.users_manage,
    ("POST", "/api/auth/users/{user_id}/reset-password"): P.users_manage,
    # pipeline (P1)
    ("POST", "/api/candidates"): P.candidates_upload,
    ("GET", "/api/candidates"): P.candidates_read,
    ("GET", "/api/candidates/{candidate_id}"): P.candidates_read,
    ("GET", "/api/candidates/{candidate_id}/text"): P.candidates_read,
    ("GET", "/api/candidates/{candidate_id}/pdf"): P.candidates_read,
    ("GET", "/api/security/findings"): P.security_center_read,
    ("POST", "/api/answer-desk/ask"): P.answer_desk_ask,
    # scoring (P2)
    ("GET", "/api/jobs"): P.scores_read,
    ("GET", "/api/jobs/{job_id}/rubric"): P.scores_read,
    ("PUT", "/api/jobs/{job_id}/rubric"): P.rubric_edit,
    ("POST", "/api/jobs/{job_id}/rescore"): P.scores_rescore,
    ("POST", "/api/jobs/{job_id}/shortlist"): P.shortlist_propose,
    ("POST", "/api/jobs/{job_id}/candidates/{candidate_id}/status"): P.candidates_status_propose,
    ("GET", "/api/money"): P.money_read,
    ("PUT", "/api/money/settings"): P.money_edit,
    ("GET", "/api/eval/summary"): P.security_center_read,
    # trust analytics (mnasri)
    ("GET", "/api/jobs/{job_id}/stability"): P.scores_read,
    ("GET", "/api/jobs/{job_id}/team-gaps"): P.scores_read,
    ("GET", "/api/jobs/{job_id}/offer-fit"): P.scores_read,
    ("PUT", "/api/candidates/{candidate_id}/conditions"): P.offer_conditions_edit,
    ("POST", "/api/candidates/{candidate_id}/offer"): P.offer_propose,
    ("GET", "/api/jobs/{job_id}/rediscover"): P.candidates_read,
    ("POST", "/api/jobs/{job_id}/rediscover/invite"): P.talent_pool_manage,
    ("DELETE", "/api/talent-pool/{candidate_id}"): P.talent_pool_manage,
    ("GET", "/api/eval/fairness"): P.security_center_read,
    ("GET", "/api/approvals/attention"): P.approvals_attention_read,
    # workflow (P3)
    ("POST", "/api/inbox/ingest"): P.inbox_ingest,
    ("GET", "/api/inbox"): P.inbox_read,
    ("POST", "/api/inbox/{inbox_id}/release-request"): P.inbox_release_request,
    ("GET", "/api/approvals"): P.approvals_decide,
    ("POST", "/api/approvals/{item_id}/decision"): P.approvals_decide,
    ("POST", "/api/approvals/batches/{batch_id}/decision"): P.approvals_decide,
    ("POST", "/api/executor/run/{item_id}"): P.approvals_execute,
    ("GET", "/api/reviewer/stats"): P.security_center_read,
    ("GET", "/api/followups/preview"): P.followups_manage,
    ("POST", "/api/followups/run"): P.followups_manage,
    ("POST", "/api/employee-questions"): P.questions_ask,
    ("GET", "/api/employee-questions"): P.questions_read,
    ("GET", "/api/employee-questions/{question_id}"): P.questions_read,
    ("POST", "/api/employee-questions/{question_id}/reply"): P.questions_reply,
    ("GET", "/api/calendar/slots"): P.calendar_read,
    ("GET", "/api/audit"): P.audit_read,
    ("GET", "/api/audit/verify"): P.audit_read,
    ("POST", "/api/audit/anchor"): P.audit_anchor,
    ("POST", "/api/documents/request"): P.documents_request,
    ("GET", "/api/documents/mine"): P.documents_request,
    ("GET", "/api/documents/{doc_id}/download"): P.documents_read,
    ("POST", "/api/interviews/{interview_id}/scorecard"): P.interviews_scorecard,
    ("GET", "/api/interviews/reminders"): P.interviews_reminders,
    # Odoo connector
    ("GET", "/api/erp/status"): P.erp_status,
    ("GET", "/api/erp/jobs/{job_id}/applicants"): P.erp_import,
    ("POST", "/api/erp/jobs/{job_id}/import"): P.erp_import,
}


def permissions_for(role: Role) -> frozenset[Permission]:
    return ROLE_PERMISSIONS.get(role, frozenset())


def roles_with(*perms: Permission) -> frozenset[Role]:
    """Roles that hold every one of `perms`."""
    return frozenset(r for r, ps in ROLE_PERMISSIONS.items() if set(perms) <= ps)


def matrix() -> dict:
    """Read-only view for the Users page."""
    return {"permissions": [p.value for p in Permission],
            "roles": {r.value: sorted(p.value for p in ps) for r, ps in ROLE_PERMISSIONS.items()}}
