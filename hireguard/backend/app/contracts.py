"""Frozen data contracts shared by every layer (H0-1 agreement).

Rule: anything derived from stranger-written text is typed. The only strings that
cross the trust boundary are ESCO IDs, enums, ISO codes, dates and character offsets.
Changing a model here = team-wide change; announce it before merging.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, conint, constr

# ---------------------------------------------------------------- primitives

YearMonth = constr(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")  # "2021-09"


class Span(BaseModel):
    """Character offsets into SanitizeResult.visible_text (end exclusive)."""
    start: conint(ge=0)
    end: conint(ge=0)


class Lang(str, Enum):
    fr = "fr"
    en = "en"
    ar = "ar"
    de = "de"
    es = "es"
    it = "it"


class CEFR(str, Enum):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"
    native = "native"


CEFR_ORDER = ["A1", "A2", "B1", "B2", "C1", "C2", "native"]


class DegreeLevel(str, Enum):
    none = "none"
    bac = "bac"
    bts = "bts"            # BTS / BTP / technicien supérieur
    licence = "licence"    # bachelor
    master = "master"
    ingenieur = "ingenieur"
    phd = "phd"


DEGREE_ORDER = ["none", "bac", "bts", "licence", "master", "ingenieur", "phd"]

# ---------------------------------------------------------------- P1: sanitizer


class HiddenChannel(str, Enum):
    white_text = "white_text"
    tiny_font = "tiny_font"
    invisible_render = "invisible_render"
    off_page = "off_page"
    under_image = "under_image"
    annotation_metadata = "annotation_metadata"
    zero_width = "zero_width"
    homoglyph = "homoglyph"


class HiddenFinding(BaseModel):
    channel: HiddenChannel
    text: str = Field(max_length=2000)  # shown to HR ESCAPED, never sent to a model
    page: conint(ge=0)
    bbox: tuple[float, float, float, float] | None = None
    # "low" = not hidden content (an undecodable glyph): shown to HR, adds no risk. Missing = "high" (fail closed).
    severity: Literal["high", "low"] = "high"


class SanitizeResult(BaseModel):
    doc_id: str
    sha256: str
    page_count: int
    visible_text: str
    page_offsets: list[int]  # visible_text index where each page starts
    hidden_findings: list[HiddenFinding] = []


class InjectionFlag(BaseModel):
    """Signal for HR only. Never feeds a score."""
    where: Literal["visible", "hidden"]
    span: Span | None = None          # visible_text offsets when where=visible
    finding_index: int | None = None  # index into hidden_findings when where=hidden
    method: Literal["regex", "prompt_guard"]
    rule_id: str                      # e.g. "fr.ignore_instructions"
    lang: str
    score: float = 1.0

# ---------------------------------------------------------------- P1: extractor (LLM output)


class ExtractedSkill(BaseModel):
    esco_id: str = Field(pattern=r"^[a-z0-9\-]{3,64}$")
    evidence: Span


class ExtractedExperience(BaseModel):
    start: YearMonth
    end: YearMonth | None = None  # null = current
    skills: list[str] = []        # esco_ids used in this role
    evidence: Span


class ExtractedDegree(BaseModel):
    level: DegreeLevel
    year: conint(ge=1960, le=2035) | None = None
    evidence: Span


class ExtractedLanguage(BaseModel):
    iso: Lang
    cefr: CEFR


class CVExtraction(BaseModel):
    """Exactly what Qwen3 may return. No free-text field exists here, on purpose."""
    doc_language: Lang
    skills: list[ExtractedSkill] = []
    experiences: list[ExtractedExperience] = []
    degrees: list[ExtractedDegree] = []
    languages: list[ExtractedLanguage] = []


class EmailIntent(str, Enum):
    application = "application"
    interview_availability = "interview_availability"
    reschedule = "reschedule"
    withdraw = "withdraw"
    status_question = "status_question"
    document_request = "document_request"
    leave_request = "leave_request"
    other = "other"


class Urgency(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"


class EmailExtraction(BaseModel):
    language: Lang
    intent: EmailIntent
    urgency: Urgency

# ---------------------------------------------------------------- P1: validator output


class DroppedField(BaseModel):
    field: str      # "skills[3]"
    reason: str     # code-generated reason, e.g. "evidence_outside_visible_text"


class ValidSkill(BaseModel):
    esco_id: str
    label: str      # ESCO preferred label (from our DB, not the CV)
    evidence: Span
    page: int
    years: float = 0.0


class ValidatedCV(BaseModel):
    candidate_id: str
    doc_id: str
    status: Literal["ok", "needs_human"]
    skills: list[ValidSkill] = []
    years_experience: float = 0.0  # computed from dates, never from the model
    highest_degree: DegreeLevel = DegreeLevel.none
    degree_evidence: Span | None = None
    languages: list[ExtractedLanguage] = []
    dropped: list[DroppedField] = []
    injection_flags: list[InjectionFlag] = []

# ---------------------------------------------------------------- P2: rubric + score


class LanguageReq(BaseModel):
    iso: Lang
    min_cefr: CEFR


class Rubric(BaseModel):
    job_id: str
    title: str
    skill_weights: dict[str, float]          # esco_id -> weight
    min_years: float = 0
    required_degree: DegreeLevel = DegreeLevel.none
    languages: list[LanguageReq] = []
    component_weights: dict[str, float] = {"skills": 60, "experience": 20, "degree": 10, "languages": 10}


class ScoreComponent(BaseModel):
    name: Literal["skills", "experience", "degree", "languages"]
    points: float
    max_points: float
    justifications: list[str]  # template-rendered, e.g. "Python: 4.0 yrs, see p.1"
    evidence: list[Span] = []


class ScoreOutput(BaseModel):
    candidate_id: str
    job_id: str
    total: float = Field(ge=0, le=100)
    components: list[ScoreComponent]
    status: Literal["proposed", "committed"] = "proposed"
    needs_human: bool = False
    injection_flag_count: int = 0

# ---------------------------------------------------------------- P3: approvals + audit


class ApprovalKind(str, Enum):
    email_send = "email_send"
    interview_booking = "interview_booking"
    status_change = "status_change"
    shortlist_commit = "shortlist_commit"
    document_release = "document_release"
    held_email_release = "held_email_release"
    leave_request = "leave_request"
    offer = "offer"


class ApprovalStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    executed = "executed"


class Decision(BaseModel):
    user_id: str
    decision: Literal["approve", "reject"]
    at: datetime


class ApprovalItem(BaseModel):
    id: str
    kind: ApprovalKind
    risk: conint(ge=0, le=100)
    risk_level: Literal["routine", "high"]
    batch_id: str | None = None          # routine items share a batch
    title: str                           # template-rendered summary
    payload: dict[str, Any]              # typed per kind, see contracts/API.md
    diff: dict[str, Any] | None = None   # {"before": ..., "after": ...}
    required_approvals: conint(ge=1, le=2) = 1
    decisions: list[Decision] = []
    status: ApprovalStatus = ApprovalStatus.pending
    created_at: datetime
    created_by: str                      # "system" or user_id
    # is_canary is stored server-side only and NEVER serialized to reviewers


class AuditEntry(BaseModel):
    seq: int
    ts: datetime
    actor: str
    action: str           # "approval.approve", "executor.send", "doc.release", ...
    object_type: str
    object_id: str
    details: dict[str, Any]
    prev_hash: str
    hash: str             # sha256(prev_hash + canonical_json(entry without hash))

# ---------------------------------------------------------------- P4: auth


class Role(str, Enum):
    recruiter = "recruiter"
    hr_manager = "hr_manager"
    employee = "employee"
    admin = "admin"


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    role: Role
