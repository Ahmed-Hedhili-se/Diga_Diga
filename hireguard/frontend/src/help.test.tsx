// The "?" Help button: the explanations moved behind it, they did not disappear. jsdom, fetch mocked.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "./auth";
import { PageHeader } from "./components/ui";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function mock(permissions: string[] = []) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    if (url.endsWith("/auth/me")) {
      return Response.json({ user: { id: "U1", email: "h@x", display_name: "HRM", role: "hr_manager" }, role: "hr_manager",
        permissions, csrf: "c", idle_timeout_s: 1800 });
    }
    return Response.json([]);
  }));
}

const at = (path: string) =>
  render(<MemoryRouter initialEntries={[path]}><AuthProvider><PageHeader title="A page" /></AuthProvider></MemoryRouter>);

const helpButton = () => screen.getByRole("button", { name: "Help for this page" });

describe("Help button", () => {
  it("is closed at first and says so to assistive technology", () => {
    mock();
    at("/candidates");
    expect(helpButton().getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("opens a dialog with the page's words, and closes with Escape, returning focus to the button", () => {
    mock();
    at("/candidates");
    fireEvent.click(helpButton());
    expect(helpButton().getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("dialog", { name: "Help for this page" })).toBeTruthy();
    expect(screen.getByText("Words used on this page")).toBeTruthy();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(helpButton());
  });

  it("closes when the visitor clicks elsewhere", () => {
    mock();
    at("/candidates");
    fireEvent.click(helpButton());
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("is not shown on the 403 page or on an unknown page", () => {
    mock();
    at("/403");
    expect(screen.queryByRole("button", { name: "Help for this page" })).toBeNull();
    cleanup();
    at("/no-such-page");
    expect(screen.queryByRole("button", { name: "Help for this page" })).toBeNull();
  });

  it("keeps the safety wording: 'proposed' is explained on the Overview, behind the button", () => {
    mock();
    at("/overview");
    expect(screen.queryByText(/A proposed score is a suggestion/)).toBeNull();           // not under the page any more
    fireEvent.click(helpButton());
    expect(screen.getByText(/A proposed score is a suggestion/)).toBeTruthy();           // one click away
  });

  it("lists the Overview's examples only for pages this account can open", async () => {
    mock(["candidates.read", "approvals.decide"]);
    at("/overview");
    await screen.findByRole("button", { name: "Help for this page" });
    fireEvent.click(helpButton());
    expect(await screen.findByText("Inspect a candidate")).toBeTruthy();
    expect(screen.getByText("Review an approval")).toBeTruthy();
    expect(screen.queryByText("Explore a security finding")).toBeNull();                 // needs security_center.read
    expect(screen.getByText(/does not approve, send or release anything/)).toBeTruthy();
  });
});
