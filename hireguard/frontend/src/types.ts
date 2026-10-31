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
  batches: { batch_id: string; kind: ApprovalKind; items: ApprovalItem[]; chunk?: number }[];
  high_risk: ApprovalItem[];
  max_batch_size?: number;
}

export interface AttentionStats {
  max_batch_size: number;
  default_max_batch_size: number;
  recent: { canaries: number; missed: number };
  by_batch_size: { batch_size: string; canaries: number; missed: number; miss_rate: number | null; ci95: number[] | null }[];
  rule: string;
}

export interface StabilityRow {
  candidate_id: string;
  base_rank: number;
  p_top_k: number;
  rank_p05: number;
  rank_p95: number;
  label: "stable_in" | "stable_out" | "borderline";
}

export interface StabilityView {
  job_id: string;
  k: number;
  jitter: number;
  draws: number;
  candidates: StabilityRow[];
}

export interface TeamGapsView {
  job_id: string;
  team: string;
  team_size: number;
  coverage: { esco_id: string; label: string; holders: number; verified_holders: number; status: "gap" | "single_holder" | "covered" }[];
  diff: { esco_id: string; label: string; before: number | null; after: number; status: string; reason: string }[];
  proposed_rubric: unknown;
  candidates_filling_gaps: Record<string, string[]>;
}

export interface FairnessAttr {
  groups: Record<string, { n: number; selected: number; rate: number }>;
  air?: number;
  air_ci95?: number[];
  p_value?: number;
  lowest?: string;
  highest?: string;
  verdict: "ok" | "watch" | "flag" | "n/a";
  gap_by_component?: Record<string, { points: number; share: number | null }>;
  proxy: { auc: number | null; null_auc_95th?: number; proxy?: boolean };
}

export interface FairnessReport {
  status?: "not_run";
  generated_at?: string;
  extraction_mode?: string;
  scope?: string;
  n_cvs?: number;
  k_frac?: number;
  observed?: Record<string, FairnessAttr>;
  positive_control?: { design: string; school: FairnessAttr; detected: boolean };
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

// InboxItem is not frozen in contracts.py yet; rendered defensively.
export interface InboxItem {
  id: string;
  from?: string;
  sender?: string;
  subject?: string;
  received_at?: string;
  intent?: string;
  urgency?: "low" | "normal" | "high";
  candidate_id?: string | null;
  auth?: { spf?: string; dkim?: string; dmarc?: string };
  reasons?: string[];
  needs_human?: boolean;
  suspicious?: boolean;
}

export interface InboxView {
  lanes: { routine: InboxItem[]; needs_human: InboxItem[]; suspicious: InboxItem[] };
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
