import { useEffect, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { api, errMsg } from "../api";
import { usePermission } from "../auth";
import EvidenceText, { pageOfOffset } from "../components/EvidenceText";
import PdfViewer from "../components/PdfViewer";
import { Badge, ConfirmButton, Empty, ErrorBox, fmtDate, fmtNum, Loading, PageHeader, useLoad } from "../components/ui";
import type { ApprovalItem, CandidateDetail, CandidateRow, Job, ScoreOutput, Slot, Span } from "../types";

interface TextView {
  visible_text: string;
  page_offsets: number[];
}

export default function Candidates() {
  const canUpload = usePermission("candidates.upload");
  const canShortlist = usePermission("shortlist.propose");
  const canRescore = usePermission("scores.rescore");

  const jobs = useLoad(() => api<Job[]>("/jobs"));
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const jobId = params.get("job") ?? jobs.data?.[0]?.job_id ?? "";
  const selected = params.get("c");
  const [shortlist, setShortlist] = useState<Set<string>>(new Set());
  const [notice, setNotice] = useState<string | null>((location.state as { notice?: string } | null)?.notice ?? null);
  const [actionErr, setActionErr] = useState<string | null>(null);

  const rows = useLoad(
    () => (jobId ? api<CandidateRow[]>(`/candidates?job_id=${encodeURIComponent(jobId)}`) : Promise.resolve([])),
    [jobId],
  );

  useEffect(() => {
    if (location.state) window.history.replaceState({}, ""); // show the upload notice once
  }, [location.state]);

  const setSel = (c: string | null, j = jobId) => {
    const next = new URLSearchParams();
    if (j) next.set("job", j);
    if (c) next.set("c", c);
    setParams(next, { replace: true });
  };
  const say = (text: string) => {
    setActionErr(null);
    setNotice(text);
  };
  const fail = (e: unknown) => {
    setNotice(null);
    setActionErr(errMsg(e));
  };

  function toggle(id: string) {
    const next = new Set(shortlist);
    next.has(id) ? next.delete(id) : next.add(id);
    setShortlist(next);
  }

  async function proposeShortlist() {
    try {
      const item = await api<ApprovalItem>(`/jobs/${encodeURIComponent(jobId)}/shortlist`, {
        body: { candidate_ids: [...shortlist] },
      });
      say(`Shortlist sent for approval as item ${item.id}. Scores stay proposals until it is approved.`);
      setShortlist(new Set());
    } catch (e) {
      fail(e);
    }
  }

  async function rescore() {
    try {
      const out = await api<ScoreOutput[]>(`/jobs/${encodeURIComponent(jobId)}/rescore`, { method: "POST" });
      say(`${out.length} candidate(s) rescored with the current rubric. Scores stay proposals.`);
      rows.reload();
    } catch (e) {
      fail(e);
    }
  }

  return (
    <>
      <PageHeader
        title="Candidates"
        subtitle="Ranked by code from validated fields only. Scores are proposals until a shortlist is approved."
        actions={
          <div className="row">
            <select aria-label="Job" value={jobId} onChange={(e) => { setShortlist(new Set()); setSel(null, e.target.value); }}>
              {(jobs.data ?? []).map((j) => (
                <option key={j.job_id} value={j.job_id}>
                  {j.title}
                </option>
              ))}
            </select>
            <Link className="btn" to={`/rubrics?job=${encodeURIComponent(jobId)}`}>
              Edit rubric
            </Link>
            {canRescore && (
              <ConfirmButton
                label="Rescore"
                disabled={!jobId}
                title="Rescore every candidate for this job?"
                message="Scores are recomputed by code from the validated CV fields and the current rubric. They stay proposals."
                confirmLabel="Rescore"
                onConfirm={rescore}
              />
            )}
            {canUpload && (
              <Link className="btn primary" to={`/candidates/upload?job=${encodeURIComponent(jobId)}`}>
                Upload CV
              </Link>
            )}
          </div>
        }
      />
      <ErrorBox error={jobs.error || rows.error || actionErr} />
      {notice && (
        <div className="alert ok" role="status">
          {notice}
        </div>
      )}

      <div className="split">
        <section className="panel list-pane" aria-label="Ranking">
          <div className="row between">
            <h2>Ranking</h2>
            {canShortlist && (
              <ConfirmButton
                className="btn primary small"
                label={`Propose shortlist (${shortlist.size})`}
                disabled={!shortlist.size}
                title="Send this shortlist for approval?"
                message={`${shortlist.size} candidate(s) will be proposed. An approver must commit the shortlist before anything changes.`}
                confirmLabel="Send for approval"
                onConfirm={proposeShortlist}
              />
            )}
          </div>
          <Loading show={rows.loading} rows={6} />
          {!rows.loading && !rows.data?.length && (
            <Empty>No candidates for this job yet.{canUpload ? " Upload a CV to start." : ""}</Empty>
          )}
          {!!rows.data?.length && (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    {canShortlist && <th aria-label="Shortlist" />}
                    <th>#</th>
                    <th>Candidate</th>
                    <th className="num">Score</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.data.map((r, i) => (
                    <tr
                      key={r.candidate_id}
                      className={selected === r.candidate_id ? "selected clickable" : "clickable"}
                      onClick={() => setSel(r.candidate_id)}
                      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), setSel(r.candidate_id))}
                      tabIndex={0}
                      aria-selected={selected === r.candidate_id}
                    >
                      {canShortlist && (
                        <td onClick={(e) => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            aria-label={`Shortlist ${r.name}`}
                            checked={shortlist.has(r.candidate_id)}
                            onChange={() => toggle(r.candidate_id)}
                          />
                        </td>
                      )}
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
            </div>
          )}
        </section>

        <section className="detail-pane">
          {selected ? <CandidatePanel id={selected} /> : <Empty>Select a candidate to see the evidence.</Empty>}
        </section>
      </div>
    </>
  );
}

// ---------------------------------------------------------------- candidate detail

function CandidatePanel({ id }: { id: string }) {
  const canSlots = usePermission("calendar.read");
  const canSecurity = usePermission("security_center.read"); // a recruiter would only get a 403 page
  const canStatus = usePermission("candidates.status_propose");
  const detail = useLoad(() => api<CandidateDetail>(`/candidates/${encodeURIComponent(id)}`), [id]);
  const text = useLoad(() => api<TextView>(`/candidates/${encodeURIComponent(id)}/text`), [id]);
  const [span, setSpan] = useState<Span | null>(null);
  const [view, setView] = useState<"text" | "pdf">("text");

  useEffect(() => setSpan(null), [id]);

  const d = detail.data;
  const t = text.data;
  const page = span && t ? pageOfOffset(t.page_offsets, span.start) : 0;
  const highlightStr = span && t ? t.visible_text.slice(span.start, span.end) : null;
  const highFindings = d ? d.hidden_findings.filter((f) => f.severity !== "low").length : 0;
  const lowFindings = d ? d.hidden_findings.length - highFindings : 0;
  const skills = d?.validated.skills ?? [];
  const listedOnly = skills.filter((k) => (k.support ?? "listed_only") === "listed_only").length;

  return (
    <div className="stack">
      <ErrorBox error={detail.error || text.error} />
      <Loading show={detail.loading} rows={5} />
      {d && (
        <div className="card">
          <div className="row between">
            <div>
              <h2>{d.name}</h2>
              <div className="muted small">
                {d.candidate_id} · {d.email} (verified) · {d.page_count} page(s)
              </div>
            </div>
            <div className="score-col">
              <div className="score-big">
                {d.score ? fmtNum(d.score.total, 1) : "—"}
                <span className="muted small"> / 100</span>
              </div>
              {skills.length > 0 && (
                <div className={`small ${listedOnly / skills.length >= 0.5 ? "text-warn" : "muted"}`}>
                  {listedOnly} of {skills.length} skills listed only
                </div>
              )}
            </div>
          </div>

          {(highFindings > 0 || d.validated.injection_flags.length > 0) && (
            <div className="alert danger">
              {highFindings} hidden item(s) and {d.validated.injection_flags.length} injection flag(s) were detected.
              They were stripped before extraction and did not change the score.{" "}
              {canSecurity && <Link to="/security">Open Security Center</Link>}
            </div>
          )}
          {lowFindings > 0 && (
            <div className="alert info">
              {lowFindings} undecodable character(s) (usually Arabic glyphs in a French or English PDF): shown for
              transparency, not treated as an attack.
            </div>
          )}

          {skills.length > 0 && (
            <div className="section-gap">
              <strong>Validated skills</strong>
              <div className="badges skills">
                {skills.map((k) => (
                  <span key={k.esco_id} className="skill">
                    <button className="link" onClick={() => setSpan(k.evidence)} title="Show evidence">
                      {k.label}
                    </button>
                    {k.years > 0 && <span className="muted small"> {fmtNum(k.years, 1)} y</span>}
                    {(k.support ?? "listed_only") === "listed_only" ? (
                      <Badge tone="warn">listed only</Badge>
                    ) : (
                      <Badge tone="ok">backed by a dated job</Badge>
                    )}
                  </span>
                ))}
              </div>
            </div>
          )}

          {canStatus && <StatusChange candidateId={d.candidate_id} jobId={d.job_id} />}
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
                        <button className={`link ${span === ev ? "active" : ""}`} onClick={() => setSpan(ev)} title="Show evidence">
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

      {canSlots && <FreeSlots />}

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

/** GET /calendar/slots: read-only. Booking happens through an approved interview item. */
function FreeSlots() {
  const slots = useLoad(() => api<Slot[]>("/calendar/slots"));
  return (
    <div className="card">
      <h3>Next free interview slots</h3>
      <ErrorBox error={slots.error} />
      <Loading show={slots.loading} rows={1} />
      {!slots.loading && !slots.data?.length && !slots.error && <Empty>No free slots in the next two weeks.</Empty>}
      <div className="badges">
        {(slots.data ?? []).map((s) => (
          <Badge key={s.id} tone="info">
            {fmtDate(s.start)}
          </Badge>
        ))}
      </div>
      <p className="muted small">Interviews are proposed from a candidate's email and booked only after approval.</p>
    </div>
  );
}

const HIRING_STATUSES = ["shortlisted", "interview", "offer", "hired", "rejected", "withdrawn"] as const;

/** POST /jobs/{job}/candidates/{id}/status: proposes the change; it happens only after approval (P3 H4). */
function StatusChange({ candidateId, jobId }: { candidateId: string; jobId: string }) {
  const [to, setTo] = useState<(typeof HIRING_STATUSES)[number]>("interview");
  const [result, setResult] = useState<{ tone: "ok" | "danger"; text: string } | null>(null);

  async function propose() {
    try {
      const item = await api<ApprovalItem>(
        `/jobs/${encodeURIComponent(jobId)}/candidates/${encodeURIComponent(candidateId)}/status`,
        { body: { status_to: to } },
      );
      setResult({ tone: "ok", text: `Proposed as approval item ${item.id}. Nothing changes until it is approved.` });
    } catch (e) {
      setResult({ tone: "danger", text: errMsg(e) });
    }
  }

  return (
    <div className="section-gap">
      <div className="row">
        <label className="inline">
          Hiring status
          <select value={to} onChange={(e) => setTo(e.target.value as typeof to)}>
            {HIRING_STATUSES.map((x) => (
              <option key={x} value={x}>
                {x}
              </option>
            ))}
          </select>
        </label>
        <ConfirmButton
          className="btn small"
          label="Propose status change"
          title={`Move ${candidateId} to "${to}"?`}
          message="This creates an approval item. The status changes only after a human approves and executes it."
          confirmLabel="Propose"
          onConfirm={propose}
        />
      </div>
      {result && <div className={`alert ${result.tone}`}>{result.text}</div>}
    </div>
  );
}
