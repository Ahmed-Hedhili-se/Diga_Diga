// "What would it be worth to you?" Pure arithmetic from GET /money/roi. Every default is an assumption and says so; a value
// the visitor types is marked "entered". Nothing here is a measured result.
import { useEffect, useState } from "react";
import { api, errMsg } from "../api";
import type { RoiView } from "../types";
import { Badge, fmtNum } from "./ui";

const FIELDS = [
  { key: "roles_per_year", label: "Roles you hire for per year", step: "1" },
  { key: "cvs_per_role", label: "CVs received per role", step: "10" },
  { key: "minutes_per_cv", label: "Minutes to read one CV", step: "0.5" },
  { key: "recruiter_cost_tnd_per_hour", label: "Recruiter cost (TND per hour)", step: "0.5" },
  { key: "days_saved_per_role", label: "Days saved per hire", step: "0.5" },
  { key: "vacancy_cost_tnd_per_day", label: "Cost of an empty seat (TND per day)", step: "10" },
  { key: "plan_price_tnd_per_month", label: "Plan price (TND per month)", step: "50" },
] as const;

export default function RoiCard() {
  const [typed, setTyped] = useState<Record<string, string>>({});
  const [roi, setRoi] = useState<RoiView | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(typed)) if (v.trim() !== "") qs.set(k, v.trim());
    let live = true;
    const timer = setTimeout(() => {
      api<RoiView>(`/money/roi${qs.toString() ? `?${qs}` : ""}`)
        .then((r) => { if (live) { setRoi(r); setErr(null); } })
        .catch((x) => { if (live) setErr(errMsg(x)); });
    }, 250);
    return () => { live = false; clearTimeout(timer); };
  }, [typed]);

  const o = roi?.outputs;
  const ratio = (v: number | null | undefined) => (v == null ? "n/a" : `${fmtNum(v, 1)}×`);

  return (
    <section className="card roi-card" aria-labelledby="roi-title">
      <h2 id="roi-title">What would it be worth to you?</h2>
      <p className="muted">
        Hypothesis: replace the assumptions with your own numbers. Nothing on this card is a measured result.
      </p>
      {err && <div className="alert danger" role="alert">{err}</div>}

      <div className="roi-grid">
        {FIELDS.map((f) => {
          const meta = roi?.inputs[f.key];
          const entered = (typed[f.key] ?? "").trim() !== "";
          return (
            <label key={f.key} className="roi-field">
              <span>{f.label}</span>
              <input
                type="number" inputMode="decimal" step={f.step} min={0}
                value={typed[f.key] ?? ""} placeholder={meta ? String(meta.value) : ""}
                onChange={(e) => setTyped({ ...typed, [f.key]: e.target.value })}
              />
              <span className="roi-meta">
                <Badge tone={entered ? "ok" : "warn"}>{entered ? "entered" : "assumption"}</Badge>
                {!entered && meta?.source_id && <span className="muted small">source {meta.source_id}</span>}
              </span>
            </label>
          );
        })}
      </div>

      {o && (
        <dl className="roi-out" aria-live="polite">
          <div><dt>Screening value per year</dt><dd>{fmtNum(o.screening_value_tnd)} TND</dd></div>
          <div><dt>Faster-hiring value per year</dt><dd>{fmtNum(o.faster_hiring_value_tnd)} TND</dd></div>
          <div><dt>Total value per year</dt><dd>{fmtNum(o.total_value_tnd)} TND</dd></div>
          <div><dt>Plan price per year</dt><dd>{fmtNum(o.plan_price_tnd_per_year)} TND</dd></div>
          <div><dt>Total value ÷ price</dt><dd>{ratio(o.total_value_over_price)}</dd></div>
          <div><dt>Screening only ÷ price</dt><dd>{ratio(o.screening_only_over_price)}</dd></div>
          <div><dt>Months of value to cover a year of price</dt><dd>{o.payback_months == null ? "n/a" : fmtNum(o.payback_months, 1)}</dd></div>
        </dl>
      )}
    </section>
  );
}
