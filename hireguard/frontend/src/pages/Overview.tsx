import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { emailReason } from "../lib/labels";
import { BRAND } from "../brand";
import { useAuth } from "../auth";
import { Icon, type IconName } from "../components/icons";
import PlanCard from "../components/PlanCard";
import { Badge, Empty, ErrorBox, fmtNum, Loading, PageHeader, useLoad } from "../components/ui";
import type {
  ApprovalsView, CandidateRow, EmployeeDocument, ErpApplicant, ErpStatus, InboxView, Job, KnowledgeGaps, ModelStatus,
  SecurityFinding,
} from "../types";

// One page that answers "what needs me now?" across Recruit (HireGuard) and Team (HR Nexus).
// Every panel is gated by a permission from GET /auth/me; the backend still answers 403 on its own.
// Everything here is read-only: opening a tile never approves, sends or releases anything.

const AUTO_REFRESH_MS = 30_000;

type Attention = { key: string; kind: "approval" | "inbox" | "candidate" | "odoo"; tone: "danger" | "warn"; title: string; detail: string; to: string };
const KIND_LABEL = { approval: "Approvals", inbox: "Inbox", candidate: "Candidates", odoo: "Odoo" } as const;

const skip = <T,>(): Promise<T | null> => Promise.resolve(null);

export default function Overview() {
  const { user, can } = useAuth();
  const [refreshes, setRefreshes] = useState(0);
  // reload when the refresh button is pressed or the signed-in user (and so the permissions) changes
  const tick = `${refreshes}:${user?.id ?? ""}`;
  const [auto, setAuto] = useState(true);
  const [updated, setUpdated] = useState(() => Date.now());

  const approvals = useLoad(() => (can("approvals.decide") ? api<ApprovalsView>("/approvals") : skip<ApprovalsView>()), [tick]);
  const inbox = useLoad(() => (can("inbox.read") ? api<InboxView>("/inbox") : skip<InboxView>()), [tick]);
  const jobs = useLoad(() => (can("candidates.read") ? api<Job[]>("/jobs") : skip<Job[]>()), [tick]);
  const pipeline = useLoad(
    () =>
      jobs.data
        ? Promise.all(jobs.data.map((j) => api<CandidateRow[]>(`/candidates?job_id=${encodeURIComponent(j.job_id)}`)))
        : skip<CandidateRow[][]>(),
    [jobs.data],
  );
  const findings = useLoad(() => (can("security_center.read") ? api<SecurityFinding[]>("/security/findings") : skip<SecurityFinding[]>()), [tick]);
  const gaps = useLoad(() => (can("team.read") ? api<KnowledgeGaps>("/team/knowledge-gaps?weeks=8") : skip<KnowledgeGaps>()), [tick]);
  const erp = useLoad(() => (can("erp.status") ? api<ErpStatus>("/erp/status") : skip<ErpStatus>()), [tick]);
  // Applicants waiting in Odoo that HireGuard has not screened yet, per job. A job Odoo does not know is skipped.
  const odooNew = useLoad(
    () =>
      can("erp.import") && erp.data?.connected && jobs.data
        ? Promise.allSettled(jobs.data.map((j) => api<ErpApplicant[]>(`/erp/jobs/${encodeURIComponent(j.job_id)}/applicants`)))
            .then((rs) => rs.map((r, i) => ({ job: jobs.data![i], waiting: r.status === "fulfilled" ? r.value.filter((a) => !a.imported).length : 0 })))
        : skip<{ job: Job; waiting: number }[]>(),
    [erp.data?.connected, jobs.data],
  );
  const docs = useLoad(() => (can("documents.request") ? api<EmployeeDocument[]>("/documents/mine") : skip<EmployeeDocument[]>()), [tick]);

  // Silent refresh while the tab is visible; the model check is not part of it (see ModelCard).
  useEffect(() => {
    if (!auto) return;
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, AUTO_REFRESH_MS);
    return () => window.clearInterval(id);
  }, [auto]);

  function refresh() {
    setRefreshes((t) => t + 1);
    setUpdated(Date.now());
  }

  const pending = approvals.data ? approvals.data.batches.reduce((n, b) => n + b.items.length, 0) + approvals.data.high_risk.length : 0;
  const lanes = inbox.data?.lanes;
  const laneCount = (groups?: { count: number }[]) => (groups ?? []).reduce((n, g) => n + g.count, 0);
  const rows = useMemo(() => (pipeline.data ?? []).flat(), [pipeline.data]);
  const needsHuman = rows.filter((r) => r.score?.needs_human).length;
  const contained = (findings.data ?? []).filter((f) => f.hidden_findings.length || f.injection_flags.length);
  const readyDocs = (docs.data ?? []).filter((d) => d.status === "released").length;

  const attention = useMemo<Attention[]>(() => {
    const out: Attention[] = [];
    for (const a of approvals.data?.high_risk ?? [])
      out.push({ key: a.id, kind: "approval", tone: "danger", title: a.title, detail: `High-risk ${a.kind.replace(/_/g, " ")}, ${a.decisions.length} of ${a.required_approvals} approvals`, to: "/approvals" });
    for (const g of lanes?.suspicious ?? [])
      for (const m of g.items)
        out.push({ key: m.id, kind: "inbox", tone: "danger", title: m.subject || "(no subject)", detail: `Held: ${m.reasons[0] ? emailReason(m.reasons[0]) : "sender could not be verified"}`, to: "/inbox" });
    for (const g of lanes?.needs_human ?? [])
      for (const m of g.items)
        out.push({ key: m.id, kind: "inbox", tone: "warn", title: m.subject || "(no subject)", detail: `Needs a person, from ${m.from_name || m.from}`, to: "/inbox" });
    for (const r of rows) {
      const to = `/candidates?job=${encodeURIComponent(r.job_id)}&c=${encodeURIComponent(r.candidate_id)}`;
      if (r.extraction === "none")
        out.push({ key: `${r.candidate_id}-ext`, kind: "candidate", tone: "warn", title: r.name, detail: "The model could not read this CV, so it has no score. Re-upload once the model is ready", to });
      else if (r.flags || r.hidden_high)
        out.push({ key: `${r.candidate_id}-sec`, kind: "candidate", tone: "danger", title: r.name, detail: `${r.hidden} hidden item(s), ${r.flags} injection flag(s) stripped before scoring`, to });
      else if (r.score?.needs_human)
        out.push({ key: `${r.candidate_id}-hum`, kind: "candidate", tone: "warn", title: r.name, detail: "Score needs a human check before it counts", to });
    }
    for (const o of odooNew.data ?? [])
      if (o.waiting)
        out.push({ key: `odoo-${o.job.job_id}`, kind: "odoo", tone: "warn", title: `${o.waiting} new applicant(s) in Odoo`,
          detail: `${o.job.title}: not screened yet. Use "Import from Odoo" on the Candidates page`, to: `/candidates?job=${encodeURIComponent(o.job.job_id)}` });
    return out;
  }, [approvals.data, lanes, rows, odooNew.data]);

  const jobQ = jobs.data?.[0]?.job_id ? `?job=${encodeURIComponent(jobs.data[0].job_id)}` : "";
  const anyRecruit = can("erp.import") || can("candidates.read") || can("approvals.decide") || can("inbox.read");
  const error = approvals.error || inbox.error || jobs.error || pipeline.error || findings.error || gaps.error || docs.error;

  return (
    <>
      <PageHeader
        title="Overview"
        subtitle="What needs you now. Nothing on this page approves or sends anything."
        actions={
          <div className="row">
            <Updated at={updated} />
            <label className="switch small" title="Refresh the numbers every 30 seconds while this tab is visible">
              <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />
              <span>Live</span>
            </label>
            <button className="btn" onClick={refresh}>
              Refresh
            </button>
            {can("candidates.upload") ? (
              <Link className="btn primary" to={`/candidates/upload${jobQ}`}>
                Upload a CV
              </Link>
            ) : can("approvals.decide") ? (
              <Link className="btn primary" to="/approvals">
                Review approvals
              </Link>
            ) : null}
          </div>
        }
      />
      <ErrorBox error={error} />

      {(can("model.status") || can("erp.status")) && (
        <section className="systems" aria-label="Connected systems">
          <div className="systems-grid">
            {can("model.status") && <ModelCard />}
            {can("erp.status") && <OdooCard erp={erp.data} loading={erp.loading} error={erp.error} />}
          </div>
        </section>
      )}

      {anyRecruit && (
        <AttentionList items={attention} loading={approvals.loading || inbox.loading || pipeline.loading}
          failed={!!(approvals.error || inbox.error || pipeline.error)} />
      )}

      <div className="tiles overview-tiles">
        {can("approvals.decide") && (
          <Tile to="/approvals" icon="approvals" module="approvals" label="Waiting for approval" value={approvals.data ? pending : null}
            sub={approvals.data ? `${approvals.data.high_risk.length} high-risk` : undefined} alert={!!approvals.data?.high_risk.length} />
        )}
        {can("inbox.read") && (
          <Tile to="/inbox" icon="inbox" module="inbox" label="Emails for a person" value={lanes ? laneCount(lanes.needs_human) + laneCount(lanes.suspicious) : null}
            sub={lanes ? `${laneCount(lanes.suspicious)} suspicious held, ${laneCount(lanes.routine)} routine` : undefined} alert={!!laneCount(lanes?.suspicious)} />
        )}
        {can("candidates.read") && (
          <Tile to="/candidates" icon="candidates" module="candidates" label="Candidates screened" value={pipeline.data ? rows.length : null}
            sub={pipeline.data ? `${needsHuman} need a human check in ${jobs.data?.length ?? 0} open role(s)` : undefined} />
        )}
        {can("security_center.read") && (
          <Tile to="/security" icon="attacks" module="security" label="CV attacks contained" value={findings.data ? contained.length : null}
            sub={findings.data ? `${findings.data.filter((f) => f.blocked).length} blocked outright; none reached a score` : undefined} />
        )}
        {can("documents.request") && (
          <Tile to="/documents" icon="documents" module="documents" label="My documents" value={docs.data ? docs.data.length : null}
            sub={docs.data ? `${readyDocs} ready to download` : undefined} />
        )}
      </div>

      {can("agent.plan") && <PlanCard />}

      <div className="overview-grid">
        {can("candidates.read") && (
          <section className="card" aria-labelledby="ov-pipeline">
            <div className="row between">
              <h2 id="ov-pipeline">Hiring pipeline</h2>
              <Legend />
            </div>
            <Loading show={!jobs.data && jobs.loading} rows={3} />
            {jobs.data && !jobs.data.length && <Empty>No open roles yet.</Empty>}
            {jobs.data?.map((j, i) => (
              <PipelineRow key={j.job_id} job={j} rows={pipeline.data?.[i]} />
            ))}
          </section>
        )}
        {can("team.read") && gaps.data && <KnowledgeCard gaps={gaps.data} />}
        {can("answer_desk.ask") && !can("candidates.read") && (
          <Link className="card tile-link overview-cta module-answer-desk" to="/answer-desk">
            <span className="module-chip module-answer-desk" aria-hidden="true">
              <Icon name="answers" size={18} />
            </span>
            <div>
              <strong>Ask the handbook</strong>
              <div className="muted small">Answers quote the handbook word for word, with the section. No match goes to HR.</div>
            </div>
          </Link>
        )}
      </div>
    </>
  );
}

function Updated({ at }: { at: number }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 5000);
    return () => window.clearInterval(id);
  }, []);
  const s = Math.max(0, Math.round((now - at) / 1000));
  return (
    <span className="muted small" aria-live="off">
      Updated {s < 10 ? "just now" : s < 60 ? `${s}s ago` : `${Math.floor(s / 60)} min ago`}
    </span>
  );
}

/** Counts up to the value once; jumps straight there under reduced motion. */
function useCountUp(value: number | null) {
  const [shown, setShown] = useState(value ?? 0);
  const from = useRef(0);
  useEffect(() => {
    if (value === null) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce || from.current === value) {
      setShown(value);
      from.current = value;
      return;
    }
    const start = performance.now();
    const a = from.current;
    let raf = 0;
    const step = (t: number) => {
      const p = Math.min(1, (t - start) / 600);
      const eased = 1 - Math.pow(1 - p, 3);
      setShown(Math.round(a + (value - a) * eased));
      if (p < 1) raf = requestAnimationFrame(step);
      else from.current = value;
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value]);
  return shown;
}

function Tile({ to, icon, module, label, value, sub, alert }: {
  to: string; icon: IconName; module: string; label: string; value: number | null; sub?: string; alert?: boolean;
}) {
  const shown = useCountUp(value);
  return (
    <Link to={to} className={`card tile tile-link overview-tile module-${module}${alert ? " tile-alert" : ""}`}>
      <div className="row between">
        <span className="tile-label">{label}</span>
        <span className="module-chip" aria-hidden="true">
          <Icon name={icon} size={16} />
        </span>
      </div>
      <div className="tile-value">{value === null ? <span className="skeleton-bar" style={{ width: 48 }} /> : fmtNum(shown)}</div>
      {sub && <div className="muted small">{sub}</div>}
      <span className="tile-go" aria-hidden="true">
        <Icon name="arrow" size={14} />
      </span>
    </Link>
  );
}

// ---------------------------------------------------------------- model (GET /model/status)

function ModelCard() {
  const [refresh, setRefresh] = useState(0);
  const m = useLoad(() => api<ModelStatus>(`/model/status?refresh=${refresh ? 1 : 0}`), [refresh]);
  const s = m.data;
  const state = !s ? "checking" : s.reachable && s.model_loaded ? "ready" : s.reachable || /cold start/.test(s.error ?? "") ? "warming" : "down";
  const label = { checking: "Checking…", ready: "Ready", warming: "Not ready yet", down: "Unreachable" }[state];
  const host = s ? { modal: "Modal GPU (cloud)", local: "this machine", remote: "remote host", gemini: "Google Gemini (cloud)" }[s.host] : "";
  return (
    <section className={`card model-card status-card is-${state}`} aria-labelledby="ov-model" aria-busy={m.loading}>
      <div className="status-line">
        <span className="model-dot" aria-hidden="true" />
        <h2 id="ov-model">
          AI model: <span className="model-state">{label}</span>
        </h2>
        <span className="muted small status-sub">
          {s ? (
            <>
              <code>{s.model}</code> on {host}
              {s.hosts > 1 ? ` (+${s.hosts - 1} more)` : ""}
              {s.latency_ms !== null ? `, ${fmtNum(s.latency_ms)} ms` : ""}
            </>
          ) : (
            "Checking the connection…"
          )}
        </span>
        <button className="btn small status-action" disabled={m.loading} onClick={() => setRefresh((n) => n + 1)}>
          {m.loading ? "Checking…" : "Check now"}
        </button>
      </div>
      {s?.error && <div className="small model-error">{s.error}</div>}
      {s && !s.reachable && (
        <div className="muted small">
          Uploads still work: hidden text is removed and CVs are scored by rules, but CVs the AI cannot read go to a
          person{s.groq_fallback ? " (Groq fallback is on for fictional data)" : ""}.
        </div>
      )}
      {s && !(s.reachable && s.model_loaded) && <ConnectSteps s={s} />}
      {s && (
        <details className="status-more">
          <summary>Details</summary>
          <div className="badges">
            {s.host === "gemini" && <Badge tone={s.credentials ? "warn" : "danger"}>{s.credentials ? "Cloud: CV text goes to Google" : "Google key missing"}</Badge>}
            {s.host === "modal" && <Badge tone={s.credentials ? "ok" : "danger"}>{s.credentials ? "Modal key set on backend" : "Modal key missing"}</Badge>}
            {s.host !== "modal" && s.host !== "gemini" && <Badge tone="ok">no key needed</Badge>}
          </div>
          <p className="muted small">
            The backend makes this check with its own credentials; your browser never contacts the GPU. The result is
            cached for a minute so this page does not keep a sleeping GPU awake.
          </p>
        </details>
      )}
      <ErrorBox error={m.error} />
    </section>
  );
}

/** What an administrator does to connect the model. Shown only while it is not ready. */
function ConnectSteps({ s }: { s: ModelStatus }) {
  return (
    <details className="model-howto">
      <summary>How to connect the AI model</summary>
      {s.host === "gemini" ? (
        <ol>
          <li>The Gemini key is missing or refused. Put <code>GEMINI_API_KEY=...</code> in <code>hireguard/.env</code> on the backend computer (create the key in Google AI Studio).</li>
          <li>Check that <code>HG_GEMINI_MODEL</code> is a model your key can use, then restart with <code>.\\run.ps1</code> and press Check now.</li>
          <li>Gemini is a cloud model: CV text is sent to Google. Use it for fictional or consented CVs, and switch back to the local or Modal model for real applicants (<code>HG_LLM_PROVIDER=ollama</code>).</li>
        </ol>
      ) : s.host === "modal" && !s.credentials ? (
        <ol>
          <li>Get the team's Modal key and secret (Modal dashboard, Settings, Proxy Auth Tokens).</li>
          <li>On the computer that runs the backend, copy <code>hireguard/.env.modal.example</code> to <code>hireguard/.env.modal</code> and paste both values.</li>
          <li>Restart with <code>.\run.ps1</code>, then press Check now. The first answer can take 1 to 3 minutes while the GPU starts.</li>
        </ol>
      ) : s.host === "local" ? (
        <ol>
          <li>No model is running on this computer. To use the team's cloud GPU instead, create <code>hireguard/.env.modal</code> from <code>.env.modal.example</code> with the Modal URL, key and secret.</li>
          <li>Or install Ollama and run <code>ollama pull {s.model}</code> on a computer with a GPU of 8 GB or more.</li>
          <li>Restart with <code>.\run.ps1</code>, then press Check now.</li>
        </ol>
      ) : (
        <ol>
          <li>The backend reached the model host but it is not ready. If it says cold start, wait 1 to 3 minutes and press Check now.</li>
          <li>If it says the model is not pulled, run <code>ollama pull {s.model}</code> on the model host.</li>
        </ol>
      )}
      <p className="muted small">The key stays on the backend computer. Never put it in the website or share it in chat.</p>
    </details>
  );
}

// ---------------------------------------------------------------- Odoo (GET /erp/status)

function OdooCard({ erp, loading, error }: { erp: ErpStatus | null; loading: boolean; error: string | null }) {
  const state = !erp ? "checking" : !erp.enabled ? "off" : erp.connected ? "ready" : "down";
  const label = { checking: "Checking…", off: "Not switched on", ready: "Connected", down: "Unreachable" }[state];
  const host = erp?.url ? erp.url.replace(/^https?:\/\//, "") : "";
  return (
    <section className={`card model-card status-card is-${state === "off" ? "warming" : state}`} aria-labelledby="ov-odoo" aria-busy={loading}>
      <div className="status-line">
        <span className="model-dot" aria-hidden="true" />
        <h2 id="ov-odoo">
          Odoo HR: <span className="model-state">{label}</span>
        </h2>
        <span className="muted small status-sub">
          {state === "ready" && <><code>{host}</code>, database {erp!.db}, Odoo {erp!.server_version}</>}
          {state === "down" && <>Did not answer: {erp!.error ?? "unknown error"}</>}
          {state === "off" && <>{BRAND.name} works on its own until Odoo is switched on.</>}
          {state === "checking" && "Checking the connection…"}
        </span>
      </div>
      {state === "ready" && (
        <details className="status-more">
          <summary>Details</summary>
          <p className="muted small">
            Applicants are imported and screened like an upload. Approved shortlists, emails, interviews and offers are copied back to Odoo.
          </p>
        </details>
      )}
      {(state === "down" || state === "off") && (
        <details className="model-howto">
          <summary>How to connect Odoo</summary>
          <ol>
            <li>In Odoo, open your user's Preferences, then Account Security, and create an API key.</li>
            <li>In <code>hireguard/.env</code> set <code>HG_ODOO_ENABLED=1</code>, <code>HG_ODOO_URL</code>, <code>HG_ODOO_DB</code>, <code>HG_ODOO_USER</code> and <code>HG_ODOO_API_KEY</code>.</li>
            <li>Restart with <code>.\run.ps1</code>. The key stays on the backend computer.</li>
          </ol>
        </details>
      )}
      <ErrorBox error={error} />
    </section>
  );
}

// ---------------------------------------------------------------- pipeline

function PipelineRow({ job, rows }: { job: Job; rows?: CandidateRow[] }) {
  const [open, setOpen] = useState(false);
  const committed = rows?.filter((r) => r.score?.status === "committed").length ?? 0;
  const human = rows?.filter((r) => r.score?.status !== "committed" && r.score?.needs_human).length ?? 0;
  const flagged = rows?.filter((r) => r.flags || r.hidden).length ?? 0;
  const total = rows?.length ?? 0;
  const proposed = total - committed - human;
  const days = job.open_since ? Math.max(0, Math.floor((Date.now() - new Date(job.open_since).getTime()) / 86_400_000)) : null;
  const late = days !== null && !!job.target_days && days > job.target_days;
  const pct = (n: number) => `${total ? (100 * n) / total : 0}%`;
  const top = [...(rows ?? [])].filter((r) => r.score).sort((a, b) => b.score!.total - a.score!.total).slice(0, 3);
  return (
    <div className={`pipeline-row${open ? " open" : ""}`}>
      <button type="button" className="pipeline-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        <div className="row between">
          <strong>{job.title}</strong>
          <span className="badges">
            {flagged > 0 && <Badge tone="danger">{flagged} attack(s) stripped</Badge>}
            {days !== null && (
              <Badge tone={late ? "warn" : "neutral"}>{job.target_days ? `day ${days} of ${job.target_days}` : `open ${days} days`}</Badge>
            )}
          </span>
        </div>
        {rows ? (
          <div className="stack-bar" role="img" aria-label={`${total} candidates: ${committed} committed, ${proposed} proposed, ${human} need a human check`}>
            {total === 0 && <span className="muted small">No candidates yet</span>}
            <span className="seg-ok" style={{ width: pct(committed) }} />
            <span className="seg-primary" style={{ width: pct(proposed) }} />
            <span className="seg-warn" style={{ width: pct(human) }} />
          </div>
        ) : (
          <span className="skeleton-bar" style={{ width: "100%", height: 10 }} />
        )}
        <div className="muted small">
          {total} candidate(s): {committed} committed, {proposed} proposed, {human} to check. {open ? "Hide top candidates" : "Show top candidates"}
        </div>
      </button>
      {open && (
        <div className="pipeline-top">
          {!top.length && <span className="muted small">No scored candidates yet.</span>}
          {top.map((r) => (
            <Link key={r.candidate_id} className="top-candidate" to={`/candidates?job=${encodeURIComponent(job.job_id)}&c=${encodeURIComponent(r.candidate_id)}`}>
              <span className="grow">{r.name}</span>
              <span className="score-track" aria-hidden="true">
                <span style={{ width: `${Math.min(100, r.score!.total)}%` }} />
              </span>
              <strong>{fmtNum(r.score!.total, 1)}</strong>
            </Link>
          ))}
          <Link className="link small" to={`/candidates?job=${encodeURIComponent(job.job_id)}`}>
            Open the full ranking
          </Link>
        </div>
      )}
    </div>
  );
}

function Legend() {
  return (
    <span className="legend small muted" aria-hidden="true">
      <i className="seg-ok" /> committed <i className="seg-primary" /> proposed <i className="seg-warn" /> to check
    </span>
  );
}

// ---------------------------------------------------------------- attention list

function AttentionList({ items, loading, failed }: { items: Attention[]; loading: boolean; failed: boolean }) {
  const [filter, setFilter] = useState<"all" | Attention["kind"]>("all");
  const [all, setAll] = useState(false);
  const kinds = (["approval", "inbox", "candidate"] as const).filter((k) => items.some((i) => i.kind === k));
  const shown = items.filter((i) => filter === "all" || i.kind === filter);
  const visible = all ? shown : shown.slice(0, 6);
  return (
    <section className="card" aria-labelledby="ov-attention">
      <div className="row between">
        <h2 id="ov-attention">Needs your attention</h2>
        {kinds.length > 1 && (
          <div className="seg" role="group" aria-label="Filter">
            {(["all", ...kinds] as const).map((k) => (
              <button key={k} className={filter === k ? "on" : ""} aria-pressed={filter === k} onClick={() => setFilter(k)}>
                {k === "all" ? `All ${items.length}` : `${KIND_LABEL[k]} ${items.filter((i) => i.kind === k).length}`}
              </button>
            ))}
          </div>
        )}
      </div>
      <Loading show={loading} rows={3} />
      {failed && (
        <div className="alert warn" role="alert">
          Some of your work could not be loaded, so this list may be incomplete. Refresh, or open Approvals and Inbox directly.
        </div>
      )}
      {!loading && !failed && !items.length && <Empty>Nothing is waiting for you. New items appear here as they arrive.</Empty>}
      <ul className="attention-list">
        {visible.map((i) => (
          <li key={i.key}>
            <Link to={i.to} className={`attention-item tone-${i.tone}`}>
              <Icon name={i.tone === "danger" ? "alert" : "followups"} size={16} />
              <span className="grow">
                <strong>{i.title}</strong>
                <span className="muted small">{i.detail}</span>
              </span>
              <span className="muted small">{KIND_LABEL[i.kind]}</span>
            </Link>
          </li>
        ))}
      </ul>
      {shown.length > 6 && (
        <button className="link small" onClick={() => setAll(!all)}>
          {all ? "Show fewer" : `Show all ${shown.length}`}
        </button>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- HR Nexus

function KnowledgeCard({ gaps }: { gaps: KnowledgeGaps }) {
  const weeks = gaps.weeks.filter((w) => w.no_match_share !== null);
  const max = Math.max(0.01, ...weeks.map((w) => w.no_match_share ?? 0));
  const top = gaps.sections.filter((s) => !s.suppressed && s.count).slice(0, 3);
  return (
    <Link to="/team" className="card tile-link" aria-labelledby="ov-knowledge">
      <div className="row between">
        <h2 id="ov-knowledge">Handbook coverage</h2>
        <Badge tone="info">team level, groups of {gaps.k}+</Badge>
      </div>
      <p className="small">
        {gaps.questions === null ? (
          "Too few questions to report yet (cells under k are hidden)."
        ) : (
          <>
            <strong>{fmtNum(gaps.questions)}</strong> employee questions since {gaps.since_week};{" "}
            {gaps.no_match.share === null ? "no-match share hidden" : <strong>{fmtNum(100 * gaps.no_match.share)}% had no handbook answer</strong>}.
          </>
        )}
      </p>
      {weeks.length > 1 && (
        <div className="sparkbars" role="img" aria-label="Weekly share of questions without a handbook answer">
          {weeks.map((w) => (
            <span key={w.week} title={`${w.week}: ${fmtNum(100 * (w.no_match_share ?? 0))}% no match`} style={{ height: `${Math.max(6, (100 * (w.no_match_share ?? 0)) / max)}%` }} />
          ))}
        </div>
      )}
      {top.length > 0 && <Chips label="Most asked" items={top.map((s) => `${s.section} (${s.count})`)} />}
    </Link>
  );
}

function Chips({ label, items }: { label: string; items: ReactNode[] }) {
  return (
    <div className="small">
      <span className="muted">{label}: </span>
      {items.map((x, i) => (
        <span key={i} className="badge">
          {x}
        </span>
      ))}
    </div>
  );
}
