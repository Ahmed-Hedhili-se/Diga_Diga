// Browser-side checks (Yasmina): hostile text stays text, failures never look like "no data", every change asks
// first, and permissions only shape the UI (the server stays the guard). jsdom, fetch mocked: no backend needed.
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { api } from "./api";
import { AuthProvider, usePermission } from "./auth";
import EvidenceText from "./components/EvidenceText";
import { ConfirmButton, ErrorBox } from "./components/ui";
import { OfferRule } from "./pages/Approvals";
import EmployeeDocs from "./pages/EmployeeDocs";

const HOSTILE = `Ahmed <img src=x onerror="window.pwned=1"> <script>window.pwned=1</script> <a href="javascript:alert(1)">cv</a>`;

beforeAll(() => {
  // jsdom has no modal dialog: open/close the native element the way the browser does
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () {
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
  Element.prototype.scrollIntoView = () => {};
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

type Route = (url: string, init?: RequestInit) => { status?: number; body?: unknown } | undefined;

function mockFetch(route: Route) {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    const r = route(url, init) ?? { body: [] };
    return new Response(JSON.stringify(r.body ?? {}), { status: r.status ?? 200, headers: { "Content-Type": "application/json" } });
  }));
  return calls;
}

const session = (permissions: string[]) => ({
  user: { id: "U1", email: "e@hireguard.demo", display_name: "Test", role: "employee" },
  role: "employee", permissions, csrf: "csrf-123", idle_timeout_s: 1800,
});

describe("hostile text renders as text", () => {
  it("candidate CV text with markup creates no element", () => {
    const { container } = render(<EvidenceText text={HOSTILE} pageOffsets={[0]} page={0} span={{ start: 0, end: 5 }} />);
    expect(container.querySelector("img, script, a[href^='javascript']")).toBeNull();
    expect(container.textContent).toContain('<img src=x onerror="window.pwned=1">');
    expect((window as unknown as { pwned?: number }).pwned).toBeUndefined();
  });

  it("a hostile server error message is shown as text", () => {
    const { container } = render(<ErrorBox error={`422: ${HOSTILE}`} />);
    expect(container.querySelector("img, script")).toBeNull();
    expect(container.textContent).toContain("<script>");
  });
});

describe("error states are not empty states", () => {
  it.each([
    ["403: forbidden for role", /Permission denied \(403\)/, /Hidden buttons are not the protection/],
    ["500: database is locked", /Server error \(500\)/, /not an empty result/],
    ["401: session expired", /session has ended \(401\)/, /Sign in again/],
    ["Failed to fetch", /Cannot reach the server/, /Nothing was saved/],
  ])("%s", (error, title, hint) => {
    render(<ErrorBox error={error} />);
    const box = screen.getByRole("alert");
    expect(box.textContent).toMatch(title);
    expect(box.textContent).toMatch(hint);
  });

  it("a failed list request shows the failure, never the empty message", async () => {
    mockFetch((url) => {
      if (url.endsWith("/auth/me")) return { body: session(["documents.request", "documents.read"]) };
      if (url.includes("/documents/mine")) return { status: 500, body: { detail: "database is locked" } };
    });
    render(<MemoryRouter><AuthProvider><EmployeeDocs /></AuthProvider></MemoryRouter>);
    expect(await screen.findByText(/Server error \(500\)/)).toBeTruthy();
    expect(screen.queryByText(/No requests yet/)).toBeNull();
  });
});

describe("every change asks first", () => {
  it("ConfirmButton runs the action only after the explicit confirm", async () => {
    const onConfirm = vi.fn();
    render(<ConfirmButton label="Approve" title="Approve this item?" message="It will be executed." confirmLabel="Yes, approve" onConfirm={onConfirm} />);
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(onConfirm).not.toHaveBeenCalled();
    expect(screen.getByText("It will be executed.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onConfirm).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Yes, approve" })); });
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});

describe("permissions shape the UI; the session and CSRF go with every change", () => {
  function Gate() {
    return usePermission("candidates.upload") ? <button>Upload CV</button> : <span>no upload</span>;
  }

  it("a control without the permission is not rendered", async () => {
    mockFetch((url) => (url.endsWith("/auth/me") ? { body: session([]) } : undefined));
    render(<AuthProvider><Gate /></AuthProvider>);
    expect(await screen.findByText("no upload")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Upload CV" })).toBeNull();
  });

  it("the control appears with the permission, and mutations carry the CSRF token", async () => {
    const calls = mockFetch((url) => (url.endsWith("/auth/me") ? { body: session(["candidates.upload"]) } : { body: {} }));
    render(<AuthProvider><Gate /></AuthProvider>);
    expect(await screen.findByRole("button", { name: "Upload CV" })).toBeTruthy();
    await api("/candidates", { body: { x: 1 } });
    const post = calls.find((c) => c.url === "/api/candidates")!;
    expect((post.init!.headers as Record<string, string>)["X-CSRF-Token"]).toBe("csrf-123");
    expect(post.init!.credentials).toBe("same-origin");
  });

  it("a 401 on any call signs the user out of the UI", async () => {
    mockFetch((url) => {
      if (url.endsWith("/auth/me")) return { body: session(["candidates.upload"]) };
      return { status: 401, body: { detail: "session expired" } };
    });
    render(<AuthProvider><Gate /></AuthProvider>);
    await screen.findByRole("button", { name: "Upload CV" });
    await expect(api("/candidates")).rejects.toThrow();
    await waitFor(() => expect(screen.queryByRole("button", { name: "Upload CV" })).toBeNull());
  });
});

describe("the offer approval rule (R14)", () => {
  const settings = { offer_approvals: 2, min: 1, max: 3, hr_managers: 2 };

  it("is not rendered, and not even requested, without the permission", async () => {
    const calls = mockFetch((url) => (url.endsWith("/auth/me") ? { body: session([]) } : undefined));
    render(<MemoryRouter><AuthProvider><OfferRule /></AuthProvider></MemoryRouter>);
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/auth/me"))).toBe(true));
    expect(screen.queryByText("Offer approval rule")).toBeNull();
    expect(calls.some((c) => c.url.includes("/approvals/settings"))).toBe(false);
  });

  it("warns when the rule cannot be met, and a change is sent with the CSRF token", async () => {
    const calls = mockFetch((url, init) => {
      if (url.endsWith("/auth/me")) return { body: session(["approvals.configure"]) };
      if (url.includes("/approvals/settings")) return { body: init?.method === "PUT" ? { ...settings, offer_approvals: 1 } : settings };
    });
    render(<MemoryRouter><AuthProvider><OfferRule /></AuthProvider></MemoryRouter>);
    expect(await screen.findByText("Offer approval rule")).toBeTruthy();
    // 2 HR managers and an author who cannot approve their own offer: only 1 person can approve, 2 are required
    expect(screen.getByText(/cannot be\s+completed/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "1" }));
    await screen.findByText(/need 1 HR manager/);
    const put = calls.find((c) => c.init?.method === "PUT")!;
    expect((put.init!.headers as Record<string, string>)["X-CSRF-Token"]).toBe("csrf-123");
    expect(JSON.parse(put.init!.body as string)).toEqual({ offer_approvals: 1 });
  });
});
