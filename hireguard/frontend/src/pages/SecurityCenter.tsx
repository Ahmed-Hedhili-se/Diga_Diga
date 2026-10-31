import { useState } from "react";
import { api } from "../api";
import { Badge, Empty, ErrorBox, fmtDate, Loading, PageHeader, plain, revealInvisible, useLoad } from "../components/ui";
import type { AuditEntry, AuditVerify, HiddenChannel, SecurityFinding } from "../types";

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
  const [tab, setTab] = useState<"attacks" | "audit">("attacks");
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
          </div>
        }
      />
      {tab === "attacks" ? <Attacks /> : <Audit />}
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
