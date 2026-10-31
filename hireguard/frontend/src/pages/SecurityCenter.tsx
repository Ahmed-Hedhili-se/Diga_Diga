import { useState } from "react";
import { api, errMsg } from "../api";
import { usePermission } from "../auth";
import {
  Badge, ConfirmButton, Empty, ErrorBox, fmtDate, fmtNum, Loading, PageHeader, plain, revealInvisible, useLoad,
} from "../components/ui";
import type {
  AuditAnchor, AuditEntry, AuditVerify, EvalSummary, HiddenChannel, Prf, RateStat, ReviewerStat, SecurityFinding,
} from "../types";

const CHANNEL_LABEL: Record<HiddenChannel, string> = {
  white_text: "White / background-colored text",
  tiny_font: "Tiny font",
  invisible_render: "Invisible render mode",
  off_page: "Off-page / clipped text",
  under_image: "Text hidden under an image",
  annotation_metadata: "Comments, annotations, metadata",
  zero_width: "Zero-width characters",
  homoglyph: "Homoglyphs (lookalike letters)",
};

const TABS = [
  ["attacks", "Blocked attacks"],
  ["eval", "Evaluation"],
  ["vigilance", "Reviewer vigilance"],
  ["audit", "Audit log"],
] as const;
type Tab = (typeof TABS)[number][0];

export default function SecurityCenter() {
  const [tab, setTab] = useState<Tab>("attacks");
  const canAudit = usePermission("audit.read");
  const tabs = TABS.filter(([k]) => k !== "audit" || canAudit);
  return (
    <>
      <PageHeader
        title="Security Center"
        subtitle="What attackers tried, what we stripped, how well it works, and proof that the record has not been altered."
        actions={
          <div className="seg" role="tablist" aria-label="Security Center sections">
            {tabs.map(([k, label]) => (
              <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>
                {label}
              </button>
            ))}
          </div>
        }
      />
      {tab === "attacks" && <Attacks />}
      {tab === "eval" && <Evaluation />}
      {tab === "vigilance" && <Vigilance />}
      {tab === "audit" && canAudit && <Audit />}
    </>
  );
}

function Attacks() {
  const f = useLoad(() => api<SecurityFinding[]>("/security/findings"));
  const items = (f.data ?? []).filter((x) => x.hidden_findings.length || x.injection_flags.length);
  return (
    <>
      <ErrorBox error={f.error} />
      <Loading show={f.loading} />
      {!f.loading && !items.length && <Empty>No hidden content or injection attempts detected.</Empty>}
      <div className="stack">
        {items.map((c) => (
          <div key={c.candidate_id} className="card">
            <div className="row between">
              <div>
                <h3>{c.name}</h3>
                <div className="muted small">
                  {c.candidate_id} · {c.job_id}
                </div>
              </div>
              <div className="badges">
                {c.blocked && <Badge tone="ok">neutralized</Badge>}
                <Badge tone="danger">{c.hidden_findings.filter((h) => h.severity !== "low").length} hidden</Badge>
                <Badge tone="warn">{c.injection_flags.length} flags</Badge>
              </div>
            </div>
            <p className="muted small">
              Hidden text is shown below for HR only. It never reached the extraction model and did not affect the score.
            </p>
            {c.hidden_findings.map((h, i) => {
              const flagged = c.injection_flags.filter((fl) => fl.where === "hidden" && fl.finding_index === i);
              return (
                <div key={i} className="finding">
                  <div className="row between">
                    <strong>
                      {CHANNEL_LABEL[h.channel] ?? h.channel}{" "}
                      {h.severity === "low" && <Badge>low: undecodable glyph, no risk</Badge>}
                    </strong>
                    <span className="muted small">
                      page {h.page + 1}
                      {h.bbox ? ` · bbox ${h.bbox.map((n) => Math.round(n)).join(", ")}` : ""}
                    </span>
                  </div>
                  <pre className="hidden-text">{revealInvisible(h.text)}</pre>
                  {flagged.length > 0 && (
                    <div className="badges">
                      {flagged.map((fl, j) => (
                        <Badge key={j} tone="danger">
                          {fl.method}: {fl.rule_id} ({fl.lang})
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
            {c.injection_flags.some((fl) => fl.where === "visible") && (
              <div className="finding">
                <strong>Instruction-like phrases in visible text</strong>
                <div className="badges">
                  {c.injection_flags
                    .filter((fl) => fl.where === "visible")
                    .map((fl, j) => (
                      <Badge key={j} tone="warn">
                        {fl.method}: {fl.rule_id} ({fl.lang}){fl.span ? ` @${fl.span.start}–${fl.span.end}` : ""}
                      </Badge>
                    ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </>
  );
}

// ---------------------------------------------------------------- evaluation (GET /eval/summary)

const pct = (x: number | null | undefined) => (x === null || x === undefined ? "—" : `${fmtNum(100 * x, 1)}%`);

function Evaluation() {
  const ev = useLoad(() => api<EvalSummary>("/eval/summary"));
  const s = ev.data?.sections;
  return (
    <>
      <ErrorBox error={ev.error} />
      <Loading show={ev.loading} rows={4} />
      {ev.data?.status === "not_run" && (
        <Empty>
          The evaluation has not been run yet. Run <code>python eval/harness.py</code> to produce the metrics.
        </Empty>
      )}
      {s && (
        <div className="stack">
          <p className="muted small">
            Generated {fmtDate(ev.data?.generated_at)} with {ev.data?.model ?? "?"}. Rates come with 95% exact
            (Clopper-Pearson) intervals.
          </p>
          <section className="card">
            <h2>Hidden-text attacks</h2>
            {s.attacks?.skipped ? (
              <Skipped why={s.attacks.skipped} />
            ) : s.attacks ? (
              <>
                <div className="tiles">
                  <Metric label="Attack success (lower is better)" stat={s.attacks.attack_success} />
                  <Metric label="Instruction payloads flagged" stat={s.attacks.instruction_flagged} />
                  <PrfTile label="Hidden-text detection" prf={s.attacks.hidden_text_detection} />
                  <Metric label="Detection recall" stat={s.attacks.hidden_text_detection?.recall_ci} />
                </div>
                <RateTable title="Attack success by channel" rows={s.attacks.by_channel} />
              </>
            ) : null}
          </section>
          <section className="card">
            <h2>Fairness twins</h2>
            <p className="muted small">Same CV, only the name, town or gender changes. The score must never move.</p>
            {s.twins?.skipped ? (
              <Skipped why={s.twins.skipped} />
            ) : s.twins ? (
              <>
                <div className="tiles">
                  <Metric label="Twins whose score changed (target 0)" stat={s.twins.score_changed} />
                </div>
                <RateTable title="By variant" rows={s.twins.by_variant} />
              </>
            ) : null}
          </section>
          <section className="card">
            <h2>Extraction quality</h2>
            {s.extraction?.skipped ? (
              <Skipped why={s.extraction.skipped} />
            ) : s.extraction ? (
              <div className="tiles">
                <PrfTile label={`Skills (${s.extraction.n_docs ?? 0} CVs)`} prf={s.extraction.skills} />
                <div className="card tile">
                  <div className="muted small">Years of experience, mean abs. error</div>
                  <div className="tile-value">{fmtNum(s.extraction.years_mae, 2)}</div>
                </div>
              </div>
            ) : null}
          </section>
        </div>
      )}
    </>
  );
}

function Skipped({ why }: { why: string }) {
  return <div className="alert warn">Not measured in this run: {why}</div>;
}

function Metric({ label, stat }: { label: string; stat?: RateStat }) {
  return (
    <div className="card tile">
      <div className="muted small">{label}</div>
      <div className="tile-value">{stat ? pct(stat.rate) : "—"}</div>
      <div className="muted small">{stat?.text ?? "n/a"}</div>
    </div>
  );
}

function PrfTile({ label, prf }: { label: string; prf?: Prf }) {
  return (
    <div className="card tile">
      <div className="muted small">{label}</div>
      <div className="tile-value">F1 {prf ? fmtNum(prf.f1, 2) : "—"}</div>
      <div className="muted small">
        precision {pct(prf?.precision)} · recall {pct(prf?.recall)}
      </div>
    </div>
  );
}

function RateTable({ title, rows }: { title: string; rows?: Record<string, RateStat> }) {
  const entries = Object.entries(rows ?? {});
  if (!entries.length) return null;
  return (
    <>
      <h3 className="section-title">{title}</h3>
      <table className="table">
        <tbody>
          {entries.map(([k, v]) => (
            <tr key={k}>
              <td>
                <code>{k}</code>
              </td>
              <td className="num">{v.text}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

// ---------------------------------------------------------------- reviewer vigilance (GET /reviewer/stats)

function Vigilance() {
  const st = useLoad(() => api<ReviewerStat[]>("/reviewer/stats"));
  return (
    <section className="card">
      <h2>Reviewer vigilance</h2>
      <p className="muted small">
        Every 20th approval item gets a planted twin with one defect (a swapped recipient, an unknown candidate, a 03:00
        interview). Approving one counts as a miss, and the executor runs nothing.
      </p>
      <ErrorBox error={st.error} />
      <Loading show={st.loading} />
      {!st.loading && !st.data?.length && <Empty>No decisions recorded yet.</Empty>}
      {!!st.data?.length && (
        <table className="table">
          <thead>
            <tr>
              <th>Reviewer</th>
              <th className="num">Decisions</th>
              <th className="num">Canaries caught</th>
              <th className="num">Canaries missed</th>
            </tr>
          </thead>
          <tbody>
            {st.data.map((r) => (
              <tr key={r.user_id}>
                <td>{r.user_id}</td>
                <td className="num">{r.decisions}</td>
                <td className="num">{r.canaries_caught}</td>
                <td className="num">
                  {r.canaries_missed ? <Badge tone="danger">{r.canaries_missed} missed</Badge> : <Badge tone="ok">0</Badge>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- audit (GET /audit, /audit/verify, POST /audit/anchor)

function Audit() {
  const verify = useLoad(() => api<AuditVerify>("/audit/verify"));
  const log = useLoad(() => api<AuditEntry[]>("/audit?limit=100"));
  const canAnchor = usePermission("audit.anchor");
  const [anchored, setAnchored] = useState<AuditAnchor | null>(null);
  const [error, setError] = useState<string | null>(null);
  const last = verify.data?.last_anchor as (AuditAnchor & { ts?: string }) | null | undefined;

  async function anchorNow() {
    setError(null);
    try {
      setAnchored(await api<AuditAnchor>("/audit/anchor", { method: "POST" }));
      verify.reload();
    } catch (x) {
      setError(errMsg(x));
    }
  }

  return (
    <>
      <ErrorBox error={verify.error || log.error || error} />
      {verify.data && (
        <div className={`card chain ${verify.data.ok ? "chain-ok" : "chain-broken"}`}>
          <div className="row between">
            <div>
              <h2>{verify.data.ok ? "Hash chain intact" : `Hash chain BROKEN at entry #${verify.data.broken_at}`}</h2>
              <div className="muted small">
                {verify.data.length} entries verified.{" "}
                {last
                  ? `Last anchor: entry #${last.seq} (${last.status ?? "?"}${last.ts ? `, ${fmtDate(last.ts)}` : ""}), head ${last.head_hash.slice(0, 12)}…`
                  : "Not anchored yet."}
              </div>
            </div>
            {canAnchor && (
              <ConfirmButton
                className="btn primary"
                label="Anchor audit log now"
                title="Anchor the audit log now?"
                message="The current head hash is written outside the database (a file, plus OpenTimestamps or git when available), so a later rewrite of history becomes detectable."
                confirmLabel="Anchor now"
                onConfirm={anchorNow}
              />
            )}
          </div>
          {anchored && (
            <div className="alert ok">
              Anchored entry #{anchored.seq} ({anchored.method}, {anchored.status}).
            </div>
          )}
        </div>
      )}
      <Loading show={log.loading} rows={6} />
      <div className="card section-gap">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>#</th>
                <th>Time</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Object</th>
                <th>Hash</th>
              </tr>
            </thead>
            <tbody>
              {(log.data ?? []).map((e) => (
                <tr key={e.seq} title={plain(e.details)}>
                  <td className="muted">{e.seq}</td>
                  <td className="small">{fmtDate(e.ts)}</td>
                  <td>{e.actor}</td>
                  <td>
                    <code>{e.action}</code>
                  </td>
                  <td className="small">
                    {e.object_type}/{e.object_id}
                  </td>
                  <td>
                    <code className="small">{e.hash.slice(0, 12)}…</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!log.loading && !log.data?.length && <Empty>No audit entries yet.</Empty>}
      </div>
    </>
  );
}
