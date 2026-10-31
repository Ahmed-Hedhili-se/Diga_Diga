// Mirrors backend/app/contracts.py and contracts/API.md. Keep in sync.

export type Role = "recruiter" | "hr_manager" | "employee" | "admin";

export interface User {
  id: string;
  email: string;
  display_name: string;
  role: Role;
}

export interface Span {
  start: number;
  end: number;
}

export type HiddenChannel =
  | "white_text"
  | "tiny_font"
  | "invisible_render"
  | "off_page"
  | "under_image"
  | "annotation_metadata"
  | "zero_width"
  | "homoglyph";

export interface HiddenFinding {
  channel: HiddenChannel;
  text: string;
  page: number;
  bbox: [number, number, number, number] | null;
}

export interface InjectionFlag {
  where: "visible" | "hidden";
  span: Span | null;
  finding_index: number | null;
  method: "regex" | "prompt_guard";
  rule_id: string;
  lang: string;
  score: number;
}

export interface ValidSkill {
  esco_id: string;
  label: string;
  evidence: Span;
  page: number;
  years: number;
}

export interface ValidatedCV {
  candidate_id: string;
  doc_id: string;
  status: "ok" | "needs_human";
  skills: ValidSkill[];
  years_experience: number;
  highest_degree: string;
  degree_evidence: Span | null;
  languages: { iso: string; cefr: string }[];
  dropped: { field: string; reason: string }[];
  injection_flags: InjectionFlag[];
}

export interface ScoreComponent {
  name: "skills" | "experience" | "degree" | "languages";
  points: number;
  max_points: number;
  justifications: string[];
  evidence: Span[];
}

export interface ScoreOutput {
  candidate_id: string;
  job_id: string;
  total: number;
  components: ScoreComponent[];
  status: "proposed" | "committed";
  needs_human: boolean;
  injection_flag_count: number;
}

export interface CandidateRow {
  candidate_id: string;
  name: string;
  email: string;
  job_id: string;
  status: string;
  score: ScoreOutput | null;
  flags: number;
  hidden: number;
}

export interface CandidateDetail extends CandidateRow {
  validated: ValidatedCV;
  page_count: number;
  hidden_findings: HiddenFinding[];
}

export interface Job {
  job_id: string;
  title: string;
  open_since?: string;
  target_days?: number;
  daily_vacancy_cost_tnd?: number;
}

export type ApprovalKind =
  | "email_send"
  | "interview_booking"
  | "status_change"
  | "shortlist_commit"
  | "document_release"
  | "held_email_release"
  | "leave_request"
  | "offer";

export interface Decision {
  user_id: string;
  decision: "approve" | "reject";
  at: string;
}

export interface ApprovalItem {
  id: string;
  kind: ApprovalKind;
  risk: number;
  risk_level: "routine" | "high";
  batch_id: string | null;
  title: string;
  payload: Record<string, unknown>;
  diff: { before?: unknown; after?: unknown } | null;
  required_approvals: number;
  decisions: Decision[];
  status: "pending" | "approved" | "rejected" | "executed";
  created_at: string;
  created_by: string;
}

export interface ApprovalsView {
  batches: { batch_id: string; kind: ApprovalKind; items: ApprovalItem[] }[];
  high_risk: ApprovalItem[];
}

export interface AuditEntry {
  seq: number;
  ts: string;
  actor: string;
  action: string;
  object_type: string;
  object_id: string;
  details: Record<string, unknown>;
  prev_hash: string;
  hash: string;
}

export interface AuditVerify {
  ok: boolean;
  length: number;
  broken_at: number | null;
  last_anchor: unknown;
}

export interface SecurityFinding {
  candidate_id: string;
  name: string;
  job_id: string;
  hidden_findings: HiddenFinding[];
  injection_flags: InjectionFlag[];
  blocked: boolean;
}

export interface InboxItem {
  id: string;
  received_at: string;
  from: string;
  from_name?: string | null;
  subject: string;
  body_preview?: string;
  auth: { spf?: string; dkim?: string; dmarc?: string };
  language?: string;
  intent: string | null;
  urgency: "low" | "normal" | "high" | null;
  lane: "routine" | "needs_human" | "suspicious";
  reasons: string[];
  status: string; // new | drafted | held | released | archived ...
  candidate_id: string | null;
  draft_item_ids: string[];
}

export interface InboxGroup {
  intent: string | null;
  urgency: string | null;
  count: number;
  items: InboxItem[];
}

export interface InboxView {
  lanes: { routine: InboxGroup[]; needs_human: InboxGroup[]; suspicious: InboxGroup[] };
}

export interface AnswerResult {
  kind: "answer" | "routed";
  extracts?: { text: string; section: string; page: number }[];
  ticket_id?: string;
}

export interface MoneyView {
  roles: { job_id: string; title: string; days_open: number; target_days: number; cost_of_vacancy_tnd: number }[];
  hours_saved: { cv_screening: number; emails: number; documents: number; answers: number; total: number };
  hourly_cost_tnd: number;
  roi_tnd: number;
}

export interface EmployeeDocument {
  id: string;
  type: string;
  status: string;
  requested_at?: string;
  released_at?: string | null;
}

// ---------------------------------------------------------------- auth / RBAC (P4)

export interface Session {
  user: User;
  role: Role;
  permissions: string[];
  csrf: string;
  idle_timeout_s: number;
}

export interface UserAdmin extends User {
  active: boolean;
  last_login_at: string | null;
  locked_until: string | null;
}

export interface PermissionMatrix {
  permissions: string[];
  roles: Record<Role, string[]>;
}

// ---------------------------------------------------------------- scoring (P2)

export type DegreeLevel = "none" | "bac" | "bts" | "licence" | "master" | "ingenieur" | "phd";
export type Cefr = "A1" | "A2" | "B1" | "B2" | "C1" | "C2" | "native";

export interface Rubric {
  job_id: string;
  title: string;
  skill_weights: Record<string, number>;
  min_years: number;
  required_degree: DegreeLevel;
  languages: { iso: "fr" | "en" | "ar"; min_cefr: Cefr }[];
  component_weights: Record<"skills" | "experience" | "degree" | "languages", number>;
}

export interface RateStat {
  k: number;
  n: number;
  rate: number | null;
  ci95: [number, number] | null;
  text: string;
}

export interface Prf {
  tp: number;
  fp: number;
  fn: number;
  precision: number;
  recall: number;
  f1: number;
}

export interface EvalSummary {
  status?: "not_run";
  generated_at?: string;
  model?: string;
  sections?: {
    attacks?: { skipped?: string; attack_success?: RateStat; by_channel?: Record<string, RateStat>;
      hidden_text_detection?: Prf & { recall_ci?: RateStat }; instruction_flagged?: RateStat };
    twins?: { skipped?: string; score_changed?: RateStat; by_variant?: Record<string, RateStat> };
    extraction?: { skipped?: string; n_docs?: number; skills?: Prf; years_mae?: number };
  };
}

// ---------------------------------------------------------------- workflow (P3)

export interface ReviewerStat {
  user_id: string;
  decisions: number;
  canaries_caught: number;
  canaries_missed: number;
}

export interface InterviewReminder {
  interview_id: string;
  candidate_id: string;
  interviewer_id: string;
  ended_at: string;
}

export interface SilentCandidate {
  candidate_id: string;
  job_id: string;
  lang: string;
  last_sent_at: string;
  days_silent: number;
}

export interface Slot {
  id: string;
  start: string;
  end: string;
}

export type QuestionTopic = "leave" | "salary" | "certificate" | "contract" | "other";

export interface EmployeeQuestion {
  id: string;
  topic: QuestionTopic;
  risk: number;
  status: "open" | "reply_drafted" | "answered";
  created_at: string;
  reply_item_id: string | null;
  text?: string;
}

export interface AuditAnchor {
  seq: number;
  head_hash: string;
  status?: string;
  method?: string;
  file?: string;
}

// ---------------------------------------------------------------- Odoo connector

export interface ErpStatus {
  enabled: boolean;
  connected: boolean;
  error?: string;
}

export interface ErpApplicant {
  applicant_id: number;
  candidate_id: string;
  name: string;
  email: string;
  stage: string | null;
  imported: boolean;
}
