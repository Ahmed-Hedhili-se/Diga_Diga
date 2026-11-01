import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { Icon, type IconName } from "../components/icons";
import { Badge, Empty, ErrorBox, fmtNum, Loading, PageHeader, useLoad } from "../components/ui";
import type {
  ApprovalsView, CandidateRow, EmployeeDocument, InboxView, Job, KnowledgeGaps, ModelStatus, MoneyView,
  SecurityFinding, TeamSkills,
} from "../types";

// One page that answers "what needs me now?" across Recruit (HireGuard) and Team (HR Nexus).
// Every panel is gated by a permission from GET /auth/me; the backend still answers 403 on its own.
// Everything here is read-only: opening a tile never approves, sends or releases anything.

const AUTO_REFRESH_MS = 30_000;

type Attention = { key: string; kind: "approval" | "inbox" | "candidate"; tone: "danger" | "warn"; title: string; detail: string; to: string };
const KIND_LABEL = { approval: "Approvals", inbox: "Inbox", candidate: "Candidates" } as const;

const skip = <T,>(): Promise<T | null> => Promise.resolve(null);

export default function Overview() {
  const { can } = useAuth();
  const [tick, setTick] = useState(0);
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
  const money = useLoad(() => (can("money.read") ? api<MoneyView>("/money") : skip<MoneyView>()), [tick]);
  const skills = useLoad(() => (can("team.read") ? api<TeamSkills[]>("/team/skills") : skip<TeamSkills[]>()), [tick]);
  const gaps = useLoad(() => (can("team.read") ? api<KnowledgeGaps>("/team/knowledge-gaps?weeks=8") : skip<KnowledgeGaps>()), [tick]);
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
    setTick((t) => t + 1);
    setUpdated(Date.now());
  }

  const pending = approvals.data ? approvals.data.batches.reduce((n, b) => n + b.items.length, 0) + approvals.data.high_risk.length : 0;
  const lanes = inbox.data?.lanes;
  const laneCount = (groups?: { count: number }[]) => (groups ?? []).reduce((n, g) => n + g.count, 0);
  const rows = useMemo(() => (pipeline.data ?? []).flat(), [pipeline.data]);
  const needsHuman = rows.filter((r) => r.score?.needs_human).length;
  const contained = (findings.data ?? []).filter((f) => f.hidden_findings.length || f.injection_flags.length);
  const vacancyCost = (money.data?.roles ?? []).reduce((n, r) => n + r.cost_of_vacancy_tnd, 0);
  const skillRisks = (skills.data ?? []).flatMap((t) => t.coverage.filter((c) => c.status !== "covered"));
  const readyDocs = (docs.data ?? []).filter((d) => d.status === "released").length;

  const attention = useMemo<Attention[]>(() => {
    const out: Attention[] = [];
    for (const a of approvals.data?.high_risk ?? [])
      out.push({ key: a.id, kind: "approval", tone: "danger", title: a.title, detail: `High-risk ${a.kind.replace(/_/g, " ")}, ${a.decisions.length} of ${a.required_approvals} approvals`, to: "/approvals" });
    for (const g of lanes?.suspicious ?? [])
      for (const m of g.items)
        out.push({ key: m.id, kind: "inbox", tone: "danger", title: m.subject || "(no subject)", detail: `Held: ${m.reasons[0] ?? "sender could not be verified"}`, to: "/inbox" });
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
    return out;
  }, [approvals.data, lanes, rows]);

  const anyRecruit = can("candidates.read") || can("approvals.decide") || can("inbox.read");
  const error = approvals.error || inbox.error || jobs.error || pipeline.error || findings.error || money.error || skills.error || gaps.error || docs.error;

  return (
    <>
      <PageHeader
        title="Overview"
        subtitle="What needs you across Recruit and Team. Nothing on this page approves or sends anything."
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
          </div>
        }
      />
      <ErrorBox error={error} />

      {can("model.status") && <ModelCard />}

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
        {can("money.read") && (
          <Tile to="/money" icon="vacancy" module="money" label="Cost of open roles (TND)" value={money.data ? vacancyCost : null}
            sub={money.data ? `${fmtNum(money.data.hours_saved.total)} hours saved, ROI ${fmtNum(money.data.roi_tnd)} TND` : undefined} />
        )}
        {can("team.read") && (
          <Tile to="/team" icon="team" module="team" label="Team skill risks" value={skills.data ? skillRisks.length : null}
            sub={skills.data ? `${skillRisks.filter((s) => s.status === "gap").length} gaps and ${skillRisks.filter((s) => s.status === "single_holder").length} single holders` : undefined} />
        )}
        {can("documents.request") && (
          <Tile to="/documents" icon="documents" module="documents" label="My documents" value={docs.data ? docs.data.length : null}
            sub={docs.data ? `${readyDocs} ready to download` : undefined} />
        )}
      </div>

      <QuickActions jobId={jobs.data?.[0]?.job_id} />

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
        {anyRecruit && <AttentionList items={attention} loading={!approvals.data && !inbox.data && !pipeline.data} />}
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
  const host = s ? { modal: "Modal GPU (cloud)", local: "this machine", remote: "remote host" }[s.host] : "";
  return (
    <section className={`card model-card is-${state}`} aria-labelledby="ov-model" aria-busy={m.loading}>
      <div className="model-main">
        <span className="model-dot" aria-hidden="true" />
        <div>
          <h2 id="ov-model">
            CV extraction model <span className="model-state">· {label}</span>
          </h2>
          <div className="muted small">
            {s ? (
              <>
                <code>{s.model}</code> on {host}
                {s.hosts > 1 ? ` (+${s.hosts - 1} more)` : ""}
                {s.latency_ms !== null ? `, answered in ${fmtNum(s.latency_ms)} ms` : ""}
                {s.cached ? " (checked within the last minute)" : ""}
              </>
            ) : (
              "Asking the backend whether it can reach the model…"
            )}
          </div>
          {s?.error && <div className="small model-error">{s.error}</div>}
          {s && !s.reachable && (
            <div className="muted small">
              Uploads still work: the sanitizer, detector and scorer run without the model, and candidates are marked
              for a human check{s.groq_fallback ? " (Groq fallback is on for fictional data)" : ""}.
            </div>
          )}
        </div>
      </div>
      <div className="model-side">
        <div className="badges">
          {s && <Badge tone={s.credentials || s.host !== "modal" ? "ok" : "danger"}>{s.host === "modal" ? (s.credentials ? "Modal key set on backend" : "Modal key missing") : "no key needed"}</Badge>}
        </div>
        <button className="btn small" disabled={m.loading} onClick={() => setRefresh((n) => n + 1)}>
          {m.loading ? "Checking…" : "Check now"}
        </button>
      </div>
      <p className="muted small model-note">
        The backend makes this check with its own credentials; your browser never contacts the GPU. Results are cached
        for a minute so this page does not keep a sleeping GPU awake.
      </p>
      <ErrorBox error={m.error} />
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

function AttentionList({ items, loading }: { items: Attention[]; loading: boolean }) {
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
      {!loading && !items.length && <Empty>Nothing is waiting for you. New items appear here as they arrive.</Empty>}
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

// ---------------------------------------------------------------- quick actions

function QuickActions({ jobId }: { jobId?: string }) {
  const { can } = useAuth();
  const q = jobId ? `?job=${encodeURIComponent(jobId)}` : "";
  const actions = ([
    { to: `/candidates/upload${q}`, icon: "upload", label: "Screen a CV", hint: "Drop a PDF: hidden text is stripped, then scored", show: can("candidates.upload") },
    { to: `/rubrics${q}`, icon: "evaluation", label: "Tune a rubric", hint: "See how weights change the ranking", show: can("candidates.read") },
    { to: "/approvals", icon: "approvals", label: "Review approvals", hint: "Nothing is sent without a person", show: can("approvals.decide") },
    { to: "/answer-desk", icon: "answers", label: "Ask the handbook", hint: "Quotes the source, never invents", show: can("answer_desk.ask") },
  ] as const).filter((a) => a.show);
  if (!actions.length) return null;
  return (
    <div className="quick-actions" role="group" aria-label="Quick actions">
      {actions.map((a) => (
        <Link key={a.to} to={a.to} className="quick-action">
          <Icon name={a.icon} size={18} />
          <span>
            <strong>{a.label}</strong>
            <span className="muted small">{a.hint}</span>
          </span>
        </Link>
      ))}
    </div>
  );
}
