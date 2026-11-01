// Readable text, not machine codes: Inbox and Approvals rendered with realistic data must not show anything like
// `dmarc_fail` or `ack_application`; chips are capped at two per row, most serious first. jsdom, fetch mocked by URL.
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "./auth";
import ChipList, { sortChips, type Chip } from "./components/ChipList";
import {
  ALL_CODES, emailIntent, emailReason, humanTitle, inboxStatus, permissionLabel, templateName, titleCase,
} from "./lib/labels";
import Approvals from "./pages/Approvals";
import Inbox from "./pages/Inbox";
import Overview from "./pages/Overview";

const MACHINE = /\b[a-z]+_[a-z]+\b/;

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
  Element.prototype.scrollIntoView = () => {};
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const PERMS = ["approvals.decide", "approvals.decide_high_risk", "approvals.execute", "followups.manage", "inbox.read",
  "inbox.release_request", "candidates.read"];

const item = (over: Record<string, unknown>) => ({
  id: "EML-001", received_at: "2026-11-01T09:00:00Z", from: "a@example.tn", from_name: "Amira", subject: "Retrait de candidature",
  body_preview: "Je retire ma candidature.", auth: { spf: "pass", dkim: "pass", dmarc: "pass" }, intent: "withdraw", urgency: "normal",
  lane: "needs_human", reasons: [], status: "new", candidate_id: "CAND-001", draft_item_ids: [], ...over,
});

const INBOX = {
  lanes: {
    suspicious: [{ intent: "application", urgency: "high", count: 1, items: [item({
      id: "EML-009", lane: "suspicious", status: "held", auth: { spf: "pass", dkim: "pass", dmarc: "fail" }, urgency: "high",
      reasons: ["dmarc_fail", "urgency_high", "intent_withdraw"], candidate_id: null })] }],
    needs_human: [{ intent: "withdraw", urgency: "normal", count: 1, items: [item({ reasons: ["intent_withdraw"] })] }],
    routine: [{ intent: "status_question", urgency: "normal", count: 1, items: [item({
      id: "EML-020", intent: "status_question", lane: "routine", status: "drafted", reasons: [], draft_item_ids: ["APR-1"] })] }],
  },
};

const APPROVAL = {
  id: "APR-0001", kind: "email_send", risk: 20, risk_level: "routine", batch_id: "B1", title: "Reply to CAND-001: ack_application",
  payload: {}, diff: null, required_approvals: 1, decisions: [], status: "pending", created_at: "2026-11-01T09:00:00Z", created_by: "U-rec",
};

function mock(extra: [string, unknown][] = [], permissions: string[] = PERMS) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    if (url.endsWith("/auth/me")) {
      return Response.json({ user: { id: "U1", email: "h@x", display_name: "HRM", role: "hr_manager" }, role: "hr_manager",
        permissions, csrf: "c", idle_timeout_s: 1800 });
    }
    const hit = extra.find(([prefix]) => url.startsWith(prefix));
    return Response.json(hit ? hit[1] : []);
  }));
}

const mount = (page: JSX.Element) => render(<MemoryRouter><AuthProvider>{page}</AuthProvider></MemoryRouter>);

describe("labels", () => {
  it("every known code has a readable name with no underscore", () => {
    const readable = [
      ...ALL_CODES.intents.map(emailIntent), ...ALL_CODES.reasons.map(emailReason), ...ALL_CODES.templates.map(templateName),
      ...ALL_CODES.permissions.map(permissionLabel), ...ALL_CODES.inboxStatuses.map(inboxStatus),
    ];
    expect(readable.filter((t) => MACHINE.test(t) || t.includes("_"))).toEqual([]);
  });

  it("composite and unknown codes still come out as words", () => {
    expect(emailReason("dmarc_fail")).toBe("Sender failed the DMARC check");
    expect(emailReason("intent_withdraw")).toBe("Withdraws application");
    expect(emailReason("some_new_reason")).toBe("Some new reason");
    expect(humanTitle("Reply to CAND-001: ack_application")).toBe("Reply to CAND-001: Application received");
    expect(titleCase("approvals.decide_high_risk")).toBe("Approvals decide high risk");
  });
});

describe("chips", () => {
  const chips: Chip[] = [
    { key: "a", label: "Verified sender", tone: "ok" }, { key: "b", label: "1 draft", tone: "info" },
    { key: "c", label: "Held", tone: "danger" }, { key: "d", label: "Marked urgent", tone: "warn" },
  ];

  it("sorts the most serious first", () => {
    expect(sortChips(chips).map((c) => c.tone)).toEqual(["danger", "warn", "info", "ok"]);
  });

  it("shows two and folds the rest into +N with the hidden labels available", () => {
    render(<ChipList chips={chips} />);
    expect(screen.getByText("Held")).toBeTruthy();
    expect(screen.getByText("Marked urgent")).toBeTruthy();
    expect(screen.queryByText("Verified sender")).toBeNull();
    const more = screen.getByText("+2");
    expect(more.getAttribute("title")).toBe("1 draft, Verified sender");
    expect(more.getAttribute("aria-label")).toContain("2 more");
  });
});

describe("pages show words, not codes", () => {
  it("Inbox: groups, chips and statuses are readable; a passing sender is one 'Verified sender' chip", async () => {
    mock([["/api/inbox", INBOX]]);
    mount(<Inbox />);
    expect((await screen.findAllByText(/Withdraws application/)).length).toBeGreaterThan(0);   // the group heading, and the reason chip
    expect(screen.getAllByText("Verified sender").length).toBeGreaterThan(0);          // routine mail: one check, not three
    expect(screen.queryByText("SPF pass")).toBeNull();
    expect(screen.getByText("DMARC fail")).toBeTruthy();                                // the failed check stays visible
    expect(screen.queryByText("Sender failed the DMARC check")).toBeNull();             // and is not repeated as a second chip
    expect(MACHINE.exec(document.body.textContent ?? "")).toBeNull();
  });

  it("Overview: a held email says why in words, not as `dmarc_fail`", async () => {
    mock([["/api/inbox", INBOX]], ["inbox.read"]);
    mount(<Overview />);
    expect(await screen.findByText(/Held: Sender failed the DMARC check/)).toBeTruthy();
    expect(MACHINE.exec(document.body.textContent ?? "")).toBeNull();
  });

  it("Approvals: titles and statuses are readable", async () => {
    mock([
      ["/api/approvals/attention", { max_batch_size: 10, default_max_batch_size: 10, recent: { canaries: 0, missed: 0 }, by_batch_size: [], rule: "" }],
      ["/api/approvals/settings", { offer_approvals: 2, min: 1, max: 2, hr_managers: 2 }],
      ["/api/approvals", { batches: [{ batch_id: "B1", kind: "email_send", items: [APPROVAL] }], high_risk: [] }],
    ]);
    mount(<Approvals />);
    expect(await screen.findByText(/Reply to CAND-001: Application received/)).toBeTruthy();
    expect(MACHINE.exec(document.body.textContent ?? "")).toBeNull();
  });
});
