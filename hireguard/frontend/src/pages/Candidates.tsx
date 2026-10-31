import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, errMsg } from "../api";
import EvidenceText, { pageOfOffset } from "../components/EvidenceText";
import PdfViewer from "../components/PdfViewer";
import { Badge, Empty, ErrorBox, fmtNum, Loading, PageHeader, useLoad } from "../components/ui";
import type { ApprovalItem, CandidateDetail, CandidateRow, Job, Span } from "../types";

interface TextView {
  visible_text: string;
  page_offsets: number[];
}

interface ErpStatus {
  enabled: boolean;
  connected: boolean;
  error?: string;
}

interface ErpImport {
  job_id: string;
  imported: { applicant_id: number; candidate_id: string }[];
  skipped: { applicant_id: number; reason: string }[];
}

export default function Candidates() {
  const jobs = useLoad(() => api<Job[]>("/jobs"));
  const [jobId, setJobId] = useState<string>("");
  const [selected, setSelected] = useState<string | null>(null);
  const [shortlist, setShortlist] = useState<Set<string>>(new Set());
  const [notice, setNotice] = useState<string | null>(null);
  const [actionErr, setActionErr] = useState<string | null>(null);
  const erp = useLoad(() => api<ErpStatus>("/erp/status"));
  const [importing, setImporting] = useState(false);

  useEffect(() => {
    if (!jobId && jobs.data?.length) setJobId(jobs.data[0].job_id);
  }, [jobs.data, jobId]);

  const rows = useLoad(
    () => (jobId ? api<CandidateRow[]>(`/candidates?job_id=${encodeURIComponent(jobId)}`) : Promise.resolve([])),
    [jobId],
  );

  function toggle(id: string) {
    const next = new Set(shortlist);
    next.has(id) ? next.delete(id) : next.add(id);
    setShortlist(next);
  }

  async function proposeShortlist() {
    setActionErr(null);
    try {
      const item = await api<ApprovalItem>(`/jobs/${encodeURIComponent(jobId)}/shortlist`, {
        body: { candidate_ids: [...shortlist] },
      });
      setNotice(`Shortlist sent for approval (${item.id}). Scores stay "proposed" until it is approved.`);
      setShortlist(new Set());
    } catch (e) {
      setActionErr(errMsg(e));
    }
  }

  async function importFromOdoo() {
    setActionErr(null);
    setImporting(true);
    try {
      const res = await api<ErpImport>(`/erp/jobs/${encodeURIComponent(jobId)}/import`, { method: "POST" });
      setNotice(`Odoo: ${res.imported.length} imported and screened, ${res.skipped.length} skipped.`);
      rows.reload();
    } catch (e) {
      setActionErr(errMsg(e));
    } finally {
      setImporting(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Candidates"
        subtitle="Ranked by code from validated fields only. Scores are proposals until HR commits the shortlist."
        actions={
          <div className="row">
            <select value={jobId} onChange={(e) => { setJobId(e.target.value); setSelected(null); }}>
              {(jobs.data ?? []).map((j) => (
                <option key={j.job_id} value={j.job_id}>
                  {j.job_id} · {j.title}
                </option>
              ))}
            </select>
            {erp.data?.enabled && (
              <>
                {erp.data.connected ? (
                  <Badge tone="ok">Odoo connected</Badge>
                ) : (
                  <span title={erp.data.error}>
                    <Badge tone="danger">Odoo offline</Badge>
                  </span>
                )}
                <button className="btn" disabled={!jobId || importing} onClick={importFromOdoo}>
                  {importing ? "Importing…" : "Import from Odoo"}
                </button>
              </>
            )}
          </div>
        }
      />
      <ErrorBox error={jobs.error || rows.error || actionErr} />
      {notice && <div className="alert ok">{notice}</div>}

      <div className="split">
        <section className="card list-pane">
          <div className="row between">
            <h2>Ranking</h2>
            <button className="btn primary small" disabled={!shortlist.size} onClick={proposeShortlist}>
              Propose shortlist ({shortlist.size})
            </button>
          </div>
          <Loading show={rows.loading} />
          {!rows.loading && !rows.data?.length && <Empty>No candidates for this job yet.</Empty>}
          <table className="table">
            <thead>
              <tr>
                <th />
                <th>#</th>
                <th>Candidate</th>
                <th className="num">Score</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {(rows.data ?? []).map((r, i) => (
                <tr
                  key={r.candidate_id}
                  className={selected === r.candidate_id ? "selected clickable" : "clickable"}
                  onClick={() => setSelected(r.candidate_id)}
                >
                  <td onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      aria-label={`Shortlist ${r.name}`}
                      checked={shortlist.has(r.candidate_id)}
                      onChange={() => toggle(r.candidate_id)}
                    />
                  </td>
                  <td className="muted">{i + 1}</td>
                  <td>
                    <div>{r.name}</div>
                    <div className="muted small">{r.candidate_id}</div>
                  </td>
                  <td className="num strong">{r.score ? fmtNum(r.score.total, 1) : "—"}</td>
                  <td>
                    <div className="badges">
                      {r.score?.status === "committed" ? <Badge tone="ok">committed</Badge> : <Badge>proposed</Badge>}
                      {r.score?.needs_human && <Badge tone="warn">needs human</Badge>}
                      {r.hidden > 0 && <Badge tone="danger">{r.hidden} hidden</Badge>}
                      {r.flags > 0 && <Badge tone="danger">{r.flags} injection flags</Badge>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="detail-pane">
          {selected ? <CandidatePanel id={selected} /> : <Empty>Select a candidate to see the evidence.</Empty>}
        </section>
      </div>
    </>
  );
}

function CandidatePanel({ id }: { id: string }) {
  const detail = useLoad(() => api<CandidateDetail>(`/candidates/${encodeURIComponent(id)}`), [id]);
  const text = useLoad(() => api<TextView>(`/candidates/${encodeURIComponent(id)}/text`), [id]);
  const [span, setSpan] = useState<Span | null>(null);
  const [view, setView] = useState<"text" | "pdf">("text");

  useEffect(() => setSpan(null), [id]);

  const d = detail.data;
  const t = text.data;
  const page = span && t ? pageOfOffset(t.page_offsets, span.start) : 0;
  const highlightStr = span && t ? t.visible_text.slice(span.start, span.end) : null;

  return (
    <div className="stack">
      <ErrorBox error={detail.error || text.error} />
      <Loading show={detail.loading} />
      {d && (
        <div className="card">
          <div className="row between">
            <div>
              <h2>{d.name}</h2>
              <div className="muted small">
                {d.candidate_id} · {d.email} (verified) · {d.page_count} page(s)
              </div>
            </div>
            <div className="score-big">
              {d.score ? fmtNum(d.score.total, 1) : "—"}
              <span className="muted small"> / 100</span>
            </div>
          </div>

          {(d.hidden_findings.length > 0 || d.validated.injection_flags.length > 0) && (
            <div className="alert danger">
              {d.hidden_findings.length} hidden item(s) and {d.validated.injection_flags.length} injection flag(s) were
              detected. They were stripped before extraction and did not change the score.{" "}
              <Link to="/security">Open Security Center</Link>
            </div>
          )}
          {d.validated.status === "needs_human" && (
            <div className="alert warn">Extraction failed validation twice. A human must review this CV.</div>
          )}

          {d.score?.components.map((c) => (
            <div key={c.name} className="component">
              <div className="row between">
                <strong className="cap">{c.name}</strong>
                <span>
                  {fmtNum(c.points, 1)} / {fmtNum(c.max_points, 0)}
                </span>
              </div>
              <div className="bar">
                <div style={{ width: `${c.max_points ? (100 * c.points) / c.max_points : 0}%` }} />
              </div>
              <ul className="justifications">
                {c.justifications.map((j, i) => {
                  const ev = c.evidence[i];
                  return (
                    <li key={i}>
                      {ev ? (
                        <button
                          className={`link ${span === ev ? "active" : ""}`}
                          onClick={() => setSpan(ev)}
                          title="Show evidence"
                        >
                          {j}
                        </button>
                      ) : (
                        <span>{j}</span>
                      )}
                    </li>
                  );
                })}
                {c.evidence.slice(c.justifications.length).map((ev, i) => (
                  <li key={`x${i}`}>
                    <button className="link" onClick={() => setSpan(ev)}>
                      evidence #{c.justifications.length + i + 1}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}

          {d.validated.dropped.length > 0 && (
            <details>
              <summary className="muted">{d.validated.dropped.length} field(s) dropped by the validator</summary>
              <ul className="small">
                {d.validated.dropped.map((x, i) => (
                  <li key={i}>
                    <code>{x.field}</code>: {x.reason}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}

      {t && (
        <div className="card">
          <div className="row between">
            <h3>Evidence {span ? `(page ${page + 1})` : ""}</h3>
            <div className="seg">
              <button className={view === "text" ? "on" : ""} onClick={() => setView("text")}>
                Visible text
              </button>
              <button className={view === "pdf" ? "on" : ""} onClick={() => setView("pdf")}>
                PDF
              </button>
            </div>
          </div>
          {view === "text" ? (
            <EvidenceText text={t.visible_text} pageOffsets={t.page_offsets} page={page} span={span} />
          ) : (
            <PdfViewer src={`/candidates/${encodeURIComponent(id)}/pdf`} page={page} highlight={highlightStr} />
          )}
        </div>
      )}
    </div>
  );
}
