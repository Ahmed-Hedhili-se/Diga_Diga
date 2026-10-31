// Talent pool rediscovery and offer fit (mnasri's trust analytics), shown under the ranking. Every action becomes an
// approval item or an audited record; buttons follow the session's permissions, the server stays the guard.
import { FormEvent, useState } from "react";
import { api, errMsg } from "../api";
import { usePermission } from "../auth";
import { Badge, ConfirmButton, Empty, ErrorBox, fmtDate, fmtNum, Loading, useLoad } from "../components/ui";
import type { ApprovalItem, Conditions, OfferFitView, RediscoverView, WorkMode } from "../types";

const FIT_TONE = { fit: "ok", negotiable: "warn", mismatch: "danger", unknown: "neutral" } as const;
const MODES: WorkMode[] = ["onsite", "hybrid", "remote"];

export function TalentPool({ jobId }: { jobId: string }) {
  const canManage = usePermission("talent_pool.manage");
  const pool = useLoad(() => api<RediscoverView>(`/jobs/${encodeURIComponent(jobId)}/rediscover`), [jobId]);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function invite() {
    try {
      const items = await api<ApprovalItem[]>(`/jobs/${encodeURIComponent(jobId)}/rediscover/invite`, {
        body: { candidate_ids: [...picked] },
      });
      setMsg(`${items.length} invitation(s) drafted. They are sent only after approval.`);
      setPicked(new Set());
      setErr(null);
    } catch (e) {
      setErr(errMsg(e));
    }
  }

  async function remove(id: string) {
    try {
      await api(`/talent-pool/${encodeURIComponent(id)}`, { method: "DELETE" });
      setMsg(`${id} removed from the talent pool (audited). They will not be rediscovered again.`);
      setErr(null);
      pool.reload();
    } catch (e) {
      setErr(errMsg(e));
    }
  }

  const rows = pool.data?.candidates ?? [];
  return (
    <section className="card" aria-label="Talent pool">
      <div className="row between">
        <div>
          <h2>Talent pool</h2>
          <div className="muted small">
            Past applicants who consented to be kept ({pool.data?.pool_days ?? "?"} days), re-scored by code with this job's
            rubric. A proposal: inviting them drafts emails that wait for approval.
          </div>
        </div>
        {canManage && (
          <ConfirmButton
            className="btn small primary"
            label={`Invite selected (${picked.size})`}
            disabled={!picked.size}
            title="Draft invitations?"
            message={`${picked.size} invitation email(s) will be drafted into the approval queue. Nothing is sent before approval.`}
            confirmLabel="Draft invitations"
            onConfirm={invite}
          />
        )}
      </div>
      <ErrorBox error={pool.error || err} />
      {msg && <div className="alert ok" role="status">{msg}</div>}
      <Loading show={pool.loading} rows={3} />
      {!pool.loading && !pool.error && !rows.length && <Empty>No consented past applicants match this job.</Empty>}
      {!!rows.length && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                {canManage && <th aria-label="Select" />}
                <th>Candidate</th>
                <th className="num">Score for this job</th>
                <th>Matched skills</th>
                <th>Consent until</th>
                {canManage && <th aria-label="Actions" />}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.candidate_id}>
                  {canManage && (
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`Select ${r.name}`}
                        checked={picked.has(r.candidate_id)}
                        onChange={() => {
                          const next = new Set(picked);
                          next.has(r.candidate_id) ? next.delete(r.candidate_id) : next.add(r.candidate_id);
                          setPicked(next);
                        }}
                      />
                    </td>
                  )}
                  <td>
                    <div>{r.name}</div>
                    <div className="muted small">
                      {r.candidate_id} · applied for {r.source_job_id}
                    </div>
                  </td>
                  <td className="num strong">
                    {fmtNum(r.total, 1)} {r.needs_human && <Badge tone="warn">needs human</Badge>}
                  </td>
                  <td className="small">{r.matched_skills.join(", ") || "—"}</td>
                  <td className="small">{fmtDate(r.consent_expires_at)}</td>
                  {canManage && (
                    <td>
                      <ConfirmButton
                        className="btn small ghost"
                        label="Remove"
                        title={`Remove ${r.name} from the talent pool?`}
                        message="Use this when the candidate asks to leave the pool. It is audited and cannot be undone."
                        confirmLabel="Remove"
                        danger
                        onConfirm={() => remove(r.candidate_id)}
                      />
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function OfferFit({ jobId, selected }: { jobId: string; selected: string | null }) {
  const view = useLoad(() => api<OfferFitView>(`/jobs/${encodeURIComponent(jobId)}/offer-fit`), [jobId]);
  const t = view.data?.terms;
  const cov = view.data?.band_coverage;
  const fit = selected ? view.data?.candidates[selected] : undefined;
  return (
    <section className="card" aria-label="Offer fit">
      <h2>Offer fit</h2>
      <div className="muted small">
        What candidates declared against the job's published terms. Shown beside the ranking, never inside it: it does
        not change any score.
      </div>
      <ErrorBox error={view.error} />
      <Loading show={view.loading} rows={2} />
      {t && (
        <p className="small">
          Pay band {t.pay_band_tnd_month[0]}–{t.pay_band_tnd_month[1]} TND/month · {t.work_mode} · {t.location} · start by{" "}
          {fmtDate(t.start_by)} · {t.contract}
        </p>
      )}
      {cov && (
        <p className="small muted">
          Top {cov.k}: {cov.declared} declared their conditions, {cov.within_band} within the pay band.
        </p>
      )}
      {selected && fit && (
        <div className="section-gap">
          <strong>{selected}</strong> <Badge tone={FIT_TONE[fit.status]}>{fit.status}</Badge>
          <ul className="small">
            {fit.checks.map((c) => (
              <li key={c.check}>
                <Badge tone={FIT_TONE[c.status]}>{c.status}</Badge> {c.check.replace("_", " ")}: {c.detail}
              </li>
            ))}
          </ul>
          <ConditionsForm id={selected} onSaved={view.reload} />
          <OfferForm id={selected} />
        </div>
      )}
      {!selected && <Empty>Select a candidate in the ranking to see their offer fit.</Empty>}
    </section>
  );
}

function ConditionsForm({ id, onSaved }: { id: string; onSaved: () => void }) {
  const can = usePermission("offers.conditions");
  const [min, setMin] = useState("");
  const [max, setMax] = useState("");
  const [modes, setModes] = useState<WorkMode[]>(["hybrid"]);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  if (!can) return null;

  async function save(e: FormEvent) {
    e.preventDefault();
    const body: Conditions = { salary_min: Number(min), work_modes: modes, ...(max ? { salary_max: Number(max) } : {}) };
    try {
      await api(`/candidates/${encodeURIComponent(id)}/conditions`, { method: "PUT", body });
      setMsg("Conditions recorded (audited).");
      setErr(null);
      onSaved();
    } catch (e2) {
      setErr(errMsg(e2));
    }
  }

  return (
    <form className="stack small" onSubmit={save} aria-label="Record declared conditions">
      <strong>Record what the candidate declared</strong>
      <div className="row">
        <label>
          Min TND/month <input type="number" min={300} max={50000} required value={min} onChange={(e) => setMin(e.target.value)} />
        </label>
        <label>
          Max <input type="number" min={300} max={50000} value={max} onChange={(e) => setMax(e.target.value)} />
        </label>
        {MODES.map((m) => (
          <label key={m}>
            <input
              type="checkbox"
              checked={modes.includes(m)}
              onChange={() => setModes(modes.includes(m) ? modes.filter((x) => x !== m) : [...modes, m])}
            />{" "}
            {m}
          </label>
        ))}
        <button className="btn small" disabled={!modes.length}>Save</button>
      </div>
      <ErrorBox error={err} />
      {msg && <div className="alert ok" role="status">{msg}</div>}
    </form>
  );
}

function OfferForm({ id }: { id: string }) {
  const can = usePermission("offers.propose");
  const [salary, setSalary] = useState("");
  const [start, setStart] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  if (!can) return null;

  async function draft() {
    try {
      const item = await api<ApprovalItem>(`/candidates/${encodeURIComponent(id)}/offer`, {
        body: { monthly_salary_tnd: Number(salary), start_date: start, lang: "fr" },
      });
      setMsg(`Offer drafted as approval item ${item.id}. It needs two HR managers before anything is sent.`);
      setErr(null);
    } catch (e) {
      setErr(errMsg(e));
    }
  }

  return (
    <div className="stack small" aria-label="Draft an offer">
      <strong>Draft an offer letter</strong>
      <div className="row">
        <label>
          Salary TND/month <input type="number" min={300} max={50000} value={salary} onChange={(e) => setSalary(e.target.value)} />
        </label>
        <label>
          Start date <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
        </label>
        <ConfirmButton
          className="btn small primary"
          label="Draft offer"
          disabled={!salary || !start}
          title="Draft this offer?"
          message="The letter goes to the approval queue and needs two different HR managers. Nothing is sent before that."
          confirmLabel="Draft offer"
          onConfirm={draft}
        />
      </div>
      <ErrorBox error={err} />
      {msg && <div className="alert ok" role="status">{msg}</div>}
    </div>
  );
}
