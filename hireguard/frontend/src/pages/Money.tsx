import { FormEvent, useEffect, useState } from "react";
import { BRAND } from "../brand";
import { api, errMsg } from "../api";
import { usePermission } from "../auth";
import RoiCard from "../components/RoiCard";
import { ErrorBox, fmtNum, Loading, PageHeader, useLoad } from "../components/ui";
import type { MoneyView } from "../types";

export default function Money() {
  const canEdit = usePermission("money.edit");
  const m = useLoad(() => api<MoneyView>("/money"));
  const [rate, setRate] = useState("");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (m.data) setRate(String(m.data.hourly_cost_tnd));
  }, [m.data]);

  async function save(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    try {
      await api("/money/settings", { method: "PUT", body: { hourly_cost_tnd: Number(rate) } });
      m.reload();
    } catch (x) {
      setErr(errMsg(x));
    }
  }

  const d = m.data;
  const maxCost = Math.max(1, ...(d?.roles.map((r) => r.cost_of_vacancy_tnd) ?? [1]));
  const hs = d?.hours_saved;

  return (
    <>
      <PageHeader title="Money dashboard" subtitle={`What open roles cost, and what ${BRAND.name} gives back. Amounts in TND.`} />
      <ErrorBox error={m.error || err} />
      <Loading show={m.loading} />
      {d && hs && (
        <>
          <div className="tiles">
            <Tile label="ROI to date" value={`${fmtNum(d.roi_tnd)} TND`} accent />
            <Tile label="Hours saved" value={fmtNum(hs.total, 1)} />
            <Tile label="Cost of open roles" value={`${fmtNum(d.roles.reduce((s, r) => s + r.cost_of_vacancy_tnd, 0))} TND`} />
            <Tile label="Hourly HR cost" value={`${fmtNum(d.hourly_cost_tnd)} TND`} />
          </div>

          <div className="grid2">
            <section className="card">
              <h2>Cost of vacancy per open role</h2>
              <table className="table">
                <thead>
                  <tr>
                    <th>Role</th>
                    <th className="num">Days open / target</th>
                    <th>Cost (TND)</th>
                  </tr>
                </thead>
                <tbody>
                  {d.roles.map((r) => (
                    <tr key={r.job_id}>
                      <td>
                        <div>{r.title}</div>
                        <div className="muted small">{r.job_id}</div>
                      </td>
                      <td className={`num ${r.days_open > r.target_days ? "text-danger" : ""}`}>
                        {r.days_open} / {r.target_days}
                      </td>
                      <td>
                        <div className="hbar">
                          <div style={{ width: `${(100 * r.cost_of_vacancy_tnd) / maxCost}%` }} />
                          <span>{fmtNum(r.cost_of_vacancy_tnd)}</span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>

            <section className="card">
              <h2>Hours saved</h2>
              {(
                [
                  ["CV screening", hs.cv_screening],
                  ["Emails drafted", hs.emails],
                  ["Documents released", hs.documents],
                  ["Questions answered", hs.answers],
                ] as [string, number][]
              ).map(([label, v]) => (
                <div key={label} className="hbar-row">
                  <span>{label}</span>
                  <div className="hbar">
                    <div style={{ width: `${hs.total ? (100 * v) / hs.total : 0}%` }} />
                    <span>{fmtNum(v, 1)} h</span>
                  </div>
                </div>
              ))}
              {canEdit && (
                <form className="row" onSubmit={save}>
                  <label className="grow">
                    Your hourly HR cost (TND)
                    <input type="number" min={1} max={1000} step="0.5" value={rate} onChange={(e) => setRate(e.target.value)} />
                  </label>
                  <button className="btn primary">Update ROI</button>
                </form>
              )}
            </section>
          </div>
          <p className="muted small">
            "ROI to date" uses assumptions: the minutes per task are our estimates and the hourly cost is the figure you set. They are not measurements.
          </p>
        </>
      )}
      <RoiCard />
    </>
  );
}

function Tile({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className={`card tile ${accent ? "accent" : ""}`}>
      <div className="muted small">{label}</div>
      <div className="tile-value">{value}</div>
    </div>
  );
}
