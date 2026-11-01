// Error vs empty on the screens the demo walks through (Yasmina, 1 Nov list): a failed request must never read as
// "nothing to do". jsdom, fetch mocked by URL.
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "./auth";
import Approvals from "./pages/Approvals";
import Overview from "./pages/Overview";

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
  Element.prototype.scrollIntoView = () => {};
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const PERMS = ["approvals.decide", "approvals.decide_high_risk", "approvals.execute", "followups.manage", "inbox.read",
  "candidates.read", "scores.read", "shortlist.propose"];

// The real response shapes (contracts/API.md), so each test fails only on what it targets
const SHAPES: [string, unknown][] = [
  ["/api/approvals/attention", { max_batch_size: 10, default_max_batch_size: 10, recent: { canaries: 0, missed: 0 }, by_batch_size: [], rule: "" }],
  ["/api/approvals/settings", { offer_approvals: 2, min: 1, max: 2, hr_managers: 2 }],
  ["/api/approvals", { batches: [], high_risk: [] }],
  ["/api/inbox", { lanes: { routine: [], needs_human: [], suspicious: [] } }],
  ["/api/model/status", { model: "qwen3:8b", host: "local", hosts: 1, credentials: false, groq_fallback: false, reachable: true }],
];

function mockFetch(fail: (url: string) => boolean) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    if (url.endsWith("/auth/me")) {
      return Response.json({ user: { id: "U1", email: "hrm@x", display_name: "HRM", role: "hr_manager" }, role: "hr_manager",
        permissions: PERMS, csrf: "c", idle_timeout_s: 1800 });
    }
    if (fail(url)) return Response.json({ detail: "database is locked" }, { status: 500 });
    const shape = SHAPES.find(([prefix]) => url.startsWith(prefix));
    return Response.json(shape ? shape[1] : []);
  }));
}

function mount(page: JSX.Element) {
  return render(<MemoryRouter><AuthProvider>{page}</AuthProvider></MemoryRouter>);
}

describe("a failed request is not an empty screen", () => {
  it("Approvals: an unreadable queue never says 'No high-risk items waiting'", async () => {
    mockFetch((u) => u.includes("/api/approvals") && !u.includes("attention") && !u.includes("rule"));
    mount(<Approvals />);
    expect(await screen.findByText(/Server error \(500\)/)).toBeTruthy();
    expect(screen.queryByText(/No high-risk items waiting/)).toBeNull();
    expect(screen.queryByText(/No routine items waiting/)).toBeNull();
  });

  it("Approvals: a failed follow-up preview never says 'No silent candidates'", async () => {
    mockFetch((u) => u.includes("/followups/preview"));
    mount(<Approvals />);
    expect(await screen.findByText(/Server error \(500\)/)).toBeTruthy();
    expect(screen.queryByText(/No silent candidates/)).toBeNull();
  });

  it("Overview: when the queue and inbox fail, it warns instead of 'Nothing is waiting for you'", async () => {
    mockFetch((u) => u.includes("/api/approvals") || u.includes("/api/inbox"));
    mount(<Overview />);
    expect(await screen.findByText(/could not be loaded, so this list may be incomplete/)).toBeTruthy();
    expect(screen.queryByText(/Nothing is waiting for you/)).toBeNull();
  });

  it("Approvals: with an answer that is really empty, the empty messages do show", async () => {
    mockFetch(() => false);
    mount(<Approvals />);
    expect(await screen.findByText(/No high-risk items waiting/)).toBeTruthy();
  });
});
