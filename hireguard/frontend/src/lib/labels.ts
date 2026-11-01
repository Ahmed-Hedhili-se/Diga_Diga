// Readable names for the codes the backend sends, so a person never reads `dmarc_fail` or `ack_application`.
// Sources of truth (kept in step by hand; the test in labels.test.tsx lists every code below):
//   backend/app/contracts.py  ApprovalKind, ApprovalStatus, EmailIntent, Urgency
//   backend/app/workflow/email_gate.py  the reasons an email is held or sent to a person
//   backend/data/templates  reply and document template names
//   backend/app/auth/permissions.py  permission codes
// A code that is not in a map falls back to its words in sentence case, never to the raw snake_case string.

/** "ack_application" -> "Ack application", "approvals.decide" -> "Approvals decide". */
export function titleCase(code: string): string {
  const words = code.replace(/[._]+/g, " ").trim();
  return words ? words[0].toUpperCase() + words.slice(1) : code;
}

const pick = (map: Record<string, string>, code: string) => map[code] ?? titleCase(code);

const INTENT: Record<string, string> = {
  application: "Applies for a job",
  interview_availability: "Gives interview availability",
  reschedule: "Asks to reschedule",
  withdraw: "Withdraws application",
  status_question: "Asks about their application",
  document_request: "Asks for a document",
  leave_request: "Asks for leave",
  other: "Something else",
};
export const emailIntent = (code?: string | null) => (code ? pick(INTENT, code) : "Not classified");

export const urgencyLabel = (code?: string | null) =>
  ({ high: "Urgent", low: "Low priority" } as Record<string, string>)[code ?? ""] ?? "";

/** Why an email is held or needs a person (backend/app/workflow/email_gate.py). */
const REASON: Record<string, string> = {
  no_trusted_auth_results: "No trusted sender check on this email",
  duplicate_trusted_auth_results: "Sender checks appear twice",
  display_name_contains_other_address: "Display name shows a different address",
  multiple_from_addresses: "More than one From address",
  reply_to_domain_mismatch: "Reply-To points to another domain",
  sender_not_a_verified_candidate: "Sender is not a verified candidate",
  extraction_failed: "The email could not be read",
  urgency_high: "Marked urgent",
};

export function emailReason(code: string): string {
  if (REASON[code]) return REASON[code];
  const dmarc = code.match(/^dmarc_(.+)$/);
  if (dmarc) return dmarc[1] === "fail" ? "Sender failed the DMARC check" : `DMARC check: ${dmarc[1]}`;
  const intent = code.match(/^intent_(.+)$/);
  if (intent) return emailIntent(intent[1]);
  return titleCase(code);
}

/** How serious a reason is, so the most serious chip is shown first. */
export type Tone = "danger" | "warn" | "info" | "ok" | "neutral";
export function reasonTone(code: string): Tone {
  if (/^dmarc_|^no_trusted|^duplicate_trusted|^display_name|^multiple_from|^reply_to/.test(code)) return "danger";
  return "warn";
}

const APPROVAL_STATUS: Record<string, string> = { pending: "Waiting", approved: "Approved", rejected: "Rejected", executed: "Done" };
const INBOX_STATUS: Record<string, string> = { new: "New", drafted: "Reply drafted", held: "Held", released: "Released", closed: "Closed" };
export const laneLabel = (code: string) => pick({ routine: "Routine", needs_human: "Needs a person", suspicious: "Suspicious" }, code);
export const approvalStatus = (code: string) => pick(APPROVAL_STATUS, code);
export const inboxStatus = (code: string) => pick(INBOX_STATUS, code);

const TEMPLATE: Record<string, string> = {
  ack_application: "Application received",
  followup_reminder: "Follow-up reminder",
  interview_invite: "Interview invitation",
  offer_letter: "Offer letter",
  question_reply: "Reply to a question",
  status_update: "Status update",
  talent_invite: "Talent pool invitation",
  leave_confirmation: "Leave confirmation",
  salary_certificate: "Salary certificate",
  work_certificate: "Work certificate",
};
export const templateName = (code: string) => pick(TEMPLATE, code);

/** Approval titles come from the backend as "Reply to CAND-001: ack_application": swap the code for its name. */
export const humanTitle = (title: string) => title.replace(/\b[a-z]+(?:_[a-z]+)+\b/g, (m) => templateName(m));

const PERMISSION: Record<string, string> = {
  "candidates.read": "View candidates",
  "candidates.upload": "Upload CVs",
  "scores.read": "View scores",
  "scores.rescore": "Rescore candidates",
  "shortlist.propose": "Propose a shortlist",
  "candidates.status_propose": "Propose a status change",
  "rubric.edit": "Edit rubrics",
  "offers.conditions": "Record offer conditions",
  "offers.propose": "Propose an offer",
  "talent_pool.manage": "Manage the talent pool",
  "approvals.attention": "See reviewer attention",
  "approvals.decide": "Decide approvals",
  "approvals.decide_high_risk": "Decide high-risk approvals",
  "approvals.execute": "Execute approved items",
  "approvals.configure": "Set approval rules",
  "inbox.read": "Read the inbox",
  "inbox.release_request": "Request release of held email",
  "inbox.ingest": "Add an email to the inbox",
  "followups.manage": "Manage follow-ups",
  "calendar.read": "See the calendar",
  "interviews.scorecard": "Fill interview scorecards",
  "interviews.reminders": "Send interview reminders",
  "documents.request": "Request documents",
  "documents.read": "Read documents",
  "documents.release": "Release documents",
  "questions.ask": "Ask employee questions",
  "questions.read": "Read employee questions",
  "questions.reply": "Reply to employee questions",
  "answer_desk.ask": "Use the Answer Desk",
  "security_center.read": "Open the Security Center",
  "audit.read": "Read the audit log",
  "audit.anchor": "Anchor the audit log",
  "money.read": "View the money dashboard",
  "money.edit": "Edit money settings",
  "team.read": "View team insights",
  "users.manage": "Manage users",
  "erp.status": "See the Odoo connection",
  "erp.import": "Import from Odoo",
  "erp.configure": "Configure Odoo",
  "model.status": "See the AI model status",
  "agent.plan": "Plan the day",
};
export const permissionLabel = (code: string) => pick(PERMISSION, code);

export const ALL_CODES = {
  intents: Object.keys(INTENT), reasons: Object.keys(REASON), templates: Object.keys(TEMPLATE),
  permissions: Object.keys(PERMISSION), approvalStatuses: Object.keys(APPROVAL_STATUS), inboxStatuses: Object.keys(INBOX_STATUS),
};
