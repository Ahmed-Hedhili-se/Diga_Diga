// The ROI card on the Money page: every default says it is an assumption, a typed value says "entered", and nothing is
// shown as measured. jsdom, fetch mocked.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import RoiCard from "./components/RoiCard";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const KEYS = ["roles_per_year", "cvs_per_role", "minutes_per_cv", "recruiter_cost_tnd_per_hour",
  "days_saved_per_role", "vacancy_cost_tnd_per_day", "plan_price_tnd_per_month"];

const BASE = {
  inputs: Object.fromEntries(KEYS.map((k) => [k, { value: 1, status: "assumption", source_id: null }])),
  outputs: { cvs_per_year: 3000, screening_hours_per_year: 200, screening_value_tnd: 2840, faster_hiring_value_tnd: 18000,
    total_value_tnd: 20840, plan_price_tnd_per_year: 4800, total_value_over_price: 4.3, screening_only_over_price: 0.6, payback_months: 2.8 },
  note: "Hypothesis: replace the assumptions with your own numbers. Nothing here is a measured result.",
};

function mock() {
  const urls: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    urls.push(url);
    return Response.json(BASE);
  }));
  return urls;
}

describe("ROI card", () => {
  it("labels every input an assumption until the visitor types, and says it is a hypothesis", async () => {
    mock();
    render(<RoiCard />);
    expect(await screen.findByText(/Total value per year/)).toBeTruthy();
    expect(screen.getAllByText("assumption")).toHaveLength(7);
    expect(screen.queryByText("entered")).toBeNull();
    expect(screen.getByText(/Hypothesis: replace the assumptions with your own numbers/)).toBeTruthy();
  });

  it("marks a typed value as entered and sends only that value", async () => {
    const urls = mock();
    render(<RoiCard />);
    await screen.findByText(/Total value per year/);
    fireEvent.change(screen.getByLabelText(/Roles you hire for per year/), { target: { value: "12" } });
    await waitFor(() => expect(urls.some((u) => u.includes("roles_per_year=12"))).toBe(true));
    const last = urls[urls.length - 1];
    expect(last).toContain("roles_per_year=12");
    expect(last).not.toContain("cvs_per_role");
    expect(screen.getAllByText("assumption")).toHaveLength(6);
    expect(screen.getAllByText("entered")).toHaveLength(1);
  });

  it("shows n/a, not Infinity, when a ratio cannot be computed", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({
      ...BASE, outputs: { ...BASE.outputs, total_value_over_price: null, screening_only_over_price: null },
    })));
    render(<RoiCard />);
    expect((await screen.findAllByText("n/a")).length).toBeGreaterThanOrEqual(2);
  });
});
