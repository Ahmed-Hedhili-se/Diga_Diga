import { useState } from "react";
import { api } from "../api";
import { Badge, Empty, ErrorBox, fmtDate, Loading, PageHeader, plain, revealInvisible, useLoad } from "../components/ui";
import type { AuditEntry, AuditVerify, FairnessAttr, FairnessReport, HiddenChannel, SecurityFinding } from "../types";

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

export default function SecurityCenter() {
  const [tab, setTab] = useState<"attacks" | "audit" | "fairness">("attacks");
  return (
    <>
      <PageHeader
        title="Security Center"
        subtitle="What attackers tried, what we stripped, and proof that the record has not been altered."
        actions={
          <div className="seg">
            <button className={tab === "attacks" ? "on" : ""} onClick={() => setTab("attacks")}>
              Blocked attacks
            </button>
            <button className={tab === "audit" ? "on" : ""} onClick={() => setTab("audit")}>
              Audit log
            </button>
            <button className={tab === "fairness" ? "on" : ""} onClick={() => setTab("fairness")}>
              Fairness audit
            </button>
          </div>
        }
      />
      {tab === "attacks" ? <Attacks /> : tab === "audit" ? <Audit /> : <Fairness />}
    </>
  );
}

const VERDICT_TONE = { ok: "ok", watch: "warn", flag: "danger", "n/a": "neutral" } as const;
const ATTR_LABEL: Record<string, string> = { region: "Region", school: "School", gender: "Gender", cv_language: "CV language" };

function FairnessRow({ name, a }: { name: string; a: FairnessAttr }) {
  return (
    <tr>
      <td>{ATTR_LABEL[name] ?? name}</td>
      <td>
        <Badge tone={VERDICT_TONE[a.verdict]}>{a.verdict}</Badge>
      </td>
      <td className="num">
        {a.air !== undefined ? `${a.air.toFixed(2)} [${a.air_ci95?.[0].toFixed(2)}–${a.air_ci95?.[1].toFixed(2)}]` : "—"}
      </td>
      <td className="num">{a.p_value !== undefined ? a.p_value.toFixed(3) : "—"}</td>
      <td className="num">
        {a.proxy.auc ?? "—"} {a.proxy.proxy && <Badge tone="danger">proxy</Badge>}
      </td>
      <td className="small muted">
        {Object.entries(a.groups).map(([g, v]) => `${g} ${v.selected}/${v.n}`).join(" · ")}
      </td>
    </tr>
  );
}

function Fairness() {
  const r = useLoad(() => api<FairnessReport>("/eval/fairness"));
  const d = r.data;
  if (r.loading || r.error) return <><ErrorBox error={r.error} /><Loading show={r.loading} /></>;
  if (!d || d.status === "not_run" || !d.observed) return <Empty>Fairness audit not run yet: python eval/fairness.py</Empty>;
  const pc = d.positive_control;
  const head = (
    <thead>
      <tr>
        <th>Attribute</th><th>Verdict</th><th className="num">Adverse-impact ratio [95% CI]</th>
        <th className="num">p</th><th className="num">Proxy AUC</th><th>Shortlisted / group</th>
      </tr>
    </thead>
  );
  return (
    <div className="stack">
      <div className="alert info">
        Shortlist = top {Math.round(100 * (d.k_frac ?? 0))}% per job, {d.n_cvs} fictional CVs, extraction: {d.extraction_mode}.
        Flag = ratio below 0.8 <em>and</em> permutation p &lt; 0.05; watch = below 0.8 but not significant. Proxy = the
        attribute can be predicted from the scored fields alone.
      </div>
      <div className="card">
        <h3>Observed</h3>
        <table className="table">{head}<tbody>
          {Object.entries(d.observed).map(([k, a]) => <FairnessRow key={k} name={k} a={a} />)}
        </tbody></table>
      </div>
      {pc && (
        <div className="card">
          <div className="row between">
            <h3>Positive control: does the audit catch a planted bias?</h3>
            <Badge tone={pc.detected ? "ok" : "danger"}>{pc.detected ? "detected" : "missed"}</Badge>
          </div>
          <div className="muted small">{pc.design}</div>
          <table className="table">{head}<tbody><FairnessRow name="school" a={pc.school} /></tbody></table>
          {pc.school.gap_by_component && (
            <div className="small">
              Gap between {pc.school.highest} and {pc.school.lowest} by score component:{" "}
              {Object.entries(pc.school.gap_by_component)
                .map(([c, g]) => `${c} ${g.points > 0 ? "+" : ""}${g.points} pts${g.share !== null ? ` (${Math.round(100 * g.share)}%)` : ""}`)
                .join(" · ")}
            </div>
          )}
        </div>
      )}
    </div>
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
                <Badge tone="danger">{c.hidden_findings.length} hidden</Badge>
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
                    <strong>{CHANNEL_LABEL[h.channel] ?? h.channel}</strong>
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

function Audit() {
  const verify = useLoad(() => api<AuditVerify>("/audit/verify"));
  const log = useLoad(() => api<AuditEntry[]>("/audit?limit=100"));
  return (
    <>
      <ErrorBox error={verify.error || log.error} />
      {verify.data && (
        <div className={`alert ${verify.data.ok ? "ok" : "danger"}`}>
          {verify.data.ok
            ? `Hash chain intact: ${verify.data.length} entries verified.`
            : `Hash chain BROKEN at entry #${verify.data.broken_at}.`}{" "}
          Last anchor: {plain(verify.data.last_anchor)}
        </div>
      )}
      <Loading show={log.loading} />
      <div className="card">
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
        {!log.loading && !log.data?.length && <Empty>No audit entries yet.</Empty>}
      </div>
    </>
  );
}
