import { DragEvent, FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import * as pdfjs from "pdfjs-dist";
import { api, ApiError, errMsg } from "../api";
import { usePermission } from "../auth";
import EvidenceText, { pageOfOffset } from "../components/EvidenceText";
import PdfViewer from "../components/PdfViewer";
import {
  Badge, ConfirmButton, Empty, ErrorBox, fmtDate, fmtNum, Loading, Modal, PageHeader, useLoad,
} from "../components/ui";
import type {
  ApprovalItem, CandidateDetail, CandidateRow, Cefr, DegreeLevel, ErpApplicant, ErpStatus, Job, Rubric, ScoreOutput,
  FitStatus, OfferFit, OfferFitView, OfferTerms, RediscoverView, Slot, Span, StabilityView, TeamGapsView,
} from "../types";

interface TextView {
  visible_text: string;
  page_offsets: number[];
}

interface ErpImport {
  job_id: string;
  imported: { applicant_id: number; candidate_id: string }[];
  skipped: { applicant_id: number; reason: string }[];
}

// Server limits (backend config: HG_MAX_UPLOAD_BYTES, HG_MAX_PDF_PAGES), checked here first for a fast answer.
const MAX_BYTES = 5 * 1024 * 1024;
const MAX_PAGES = 6;
const SHORTLIST_FRAC = 0.2; // same default as the fairness audit (eval/fairness.py --k-frac)

const FIT_TONE: Record<FitStatus, "ok" | "warn" | "danger" | "neutral"> = {
  fit: "ok",
  negotiable: "warn",
  mismatch: "danger",
  unknown: "neutral",
};
const CHECK_LABEL: Record<string, string> = {
  salary: "Salary",
  start_date: "Start date",
  work_mode: "Work mode",
  commitments: "Commitments",
};

// 404 means "this job has no roster / published terms": a real absence, not an error to hide
const orNullOn404 = <T,>(p: Promise<T>) =>
  p.catch((e) => (e instanceof ApiError && e.status === 404 ? null : Promise.reject(e)));

function FitBadge({ f }: { f?: OfferFit }) {
  if (!f) return null;
  const tip = f.checks.length
    ? f.checks.map((c) => `${CHECK_LABEL[c.check] ?? c.check}: ${c.status} (${c.detail})`).join("\n")
    : "No conditions declared yet: ask, don't guess.";
  return (
    <span title={`Declared conditions vs. published terms. Not part of the score.\n${tip}`}>
      <Badge tone={FIT_TONE[f.status]}>{f.status === "unknown" ? "conditions unknown" : `offer ${f.status}`}</Badge>
    </span>
  );
}

export default function Candidates() {
  const canUpload = usePermission("candidates.upload");
  const canShortlist = usePermission("shortlist.propose");
  const canRescore = usePermission("scores.rescore");
  const canErp = usePermission("erp.import");
  const canEditRubric = usePermission("rubric.edit");
  const canPool = usePermission("talent_pool.manage");
  const canOffer = usePermission("offers.propose");

  const jobs = useLoad(() => api<Job[]>("/jobs"));
  const [jobId, setJobId] = useState<string>("");
  const [k, setK] = useState<number | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [shortlist, setShortlist] = useState<Set<string>>(new Set());
  const [notice, setNotice] = useState<string | null>(null);
  const [actionErr, setActionErr] = useState<string | null>(null);
  const [panel, setPanel] = useState<"upload" | "rubric" | null>(null);
  const [showErp, setShowErp] = useState(false);
  const erp = useLoad(() => (canErp ? api<ErpStatus>("/erp/status") : Promise.resolve(null)), [canErp]);

  useEffect(() => {
    if (!jobId && jobs.data?.length) setJobId(jobs.data[0].job_id);
  }, [jobs.data, jobId]);

  const rows = useLoad(
    () => (jobId ? api<CandidateRow[]>(`/candidates?job_id=${encodeURIComponent(jobId)}`) : Promise.resolve([])),
    [jobId],
  );
  const n = rows.data?.length ?? 0;
  const shortK = k ?? Math.max(1, Math.ceil(SHORTLIST_FRAC * n));
  const stab = useLoad(
    () => (jobId && n ? api<StabilityView>(`/jobs/${encodeURIComponent(jobId)}/stability?k=${shortK}`) : Promise.resolve(null)),
    [jobId, shortK, n],
  );
  const gaps = useLoad(
    () => (jobId ? orNullOn404(api<TeamGapsView>(`/jobs/${encodeURIComponent(jobId)}/team-gaps`)) : Promise.resolve(null)),
    [jobId],
  );
  const fit = useLoad(
    () =>
      jobId && n
        ? orNullOn404(api<OfferFitView>(`/jobs/${encodeURIComponent(jobId)}/offer-fit?k=${shortK}`))
        : Promise.resolve(null),
    [jobId, shortK, n],
  );
  const pool = useLoad(
    () => (jobId ? api<RediscoverView>(`/jobs/${encodeURIComponent(jobId)}/rediscover`) : Promise.resolve(null)),
    [jobId],
  );
  const [invite, setInvite] = useState<Set<string>>(new Set());
  const stabBy = new Map((stab.data?.candidates ?? []).map((s) => [s.candidate_id, s]));
  const fills = gaps.data?.candidates_filling_gaps ?? {};
  const bc = fit.data?.band_coverage;

  async function sendInvites() {
    setActionErr(null);
    try {
      const items = await api<ApprovalItem[]>(`/jobs/${encodeURIComponent(jobId)}/rediscover/invite`, {
        body: { candidate_ids: [...invite] },
      });
      setNotice(
        items.length
          ? `${items.length} invitation(s) drafted and sent to the approval queue. Nothing is sent before approval.`
          : "No invitation drafted: these people were already invited or their consent is no longer valid.",
      );
      setInvite(new Set());
    } catch (e) {
      setActionErr(errMsg(e));
    }
  }

  async function applyTeamWeights() {
    if (!gaps.data) return;
    setActionErr(null);
    try {
      await api(`/jobs/${encodeURIComponent(jobId)}/rubric`, { method: "PUT", body: gaps.data.proposed_rubric });
      await api(`/jobs/${encodeURIComponent(jobId)}/rescore`, { method: "POST" });
      setNotice(`Rubric updated from ${gaps.data.team} gaps (audited) and candidates rescored.`);
      rows.reload();
      stab.reload();
      gaps.reload();
    } catch (e) {
      setActionErr(errMsg(e));
    }
  }

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
      say(`Shortlist sent for approval as item ${item.id}. Scores stay "proposed" until it is approved.`);
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

  async function importFromOdoo() {
    try {
      const res = await api<ErpImport>(`/erp/jobs/${encodeURIComponent(jobId)}/import`, { method: "POST" });
      say(`Odoo: ${res.imported.length} imported and screened, ${res.skipped.length} skipped.`);
      rows.reload();
    } catch (e) {
      fail(e);
    }
  }

  const job = jobs.data?.find((j) => j.job_id === jobId);

  return (
    <>
      <PageHeader
        title="Candidates"
        subtitle="Ranked by code from validated fields only. Scores are proposals until HR commits the shortlist."
        actions={
          <div className="row">
            <select
              aria-label="Job"
              value={jobId}
              onChange={(e) => {
                setJobId(e.target.value);
                setSelected(null);
                setShortlist(new Set());
                setK(null);
              }}
            >
              {(jobs.data ?? []).map((j) => (
                <option key={j.job_id} value={j.job_id}>
                  {j.job_id} · {j.title}
                </option>
              ))}
            </select>
            <button className="btn" disabled={!jobId} onClick={() => setPanel("rubric")}>
              Rubric
            </button>
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
              <button className="btn primary" disabled={!jobId} onClick={() => setPanel("upload")}>
                Upload CV
              </button>
            )}
          </div>
        }
      />
      <ErrorBox error={jobs.error || rows.error || gaps.error || fit.error || pool.error || actionErr} />
      {notice && (
        <div className="alert ok" role="status">
          {notice}
        </div>
      )}

      {canErp && erp.data?.enabled && (
        <div className="card erp-bar">
          <div className="row between">
            <div className="row">
              <strong>Odoo</strong>
              {erp.data.connected ? (
                <Badge tone="ok">connected</Badge>
              ) : (
                <span title={erp.data.error}>
                  <Badge tone="danger">offline</Badge>
                </span>
              )}
              <span className="muted small">CVs from Odoo go through the same checks as an upload.</span>
            </div>
            <div className="row">
              <button className="btn small" disabled={!jobId} onClick={() => setShowErp(!showErp)} aria-expanded={showErp}>
                {showErp ? "Hide applicants" : "Preview applicants"}
              </button>
              <ConfirmButton
                className="btn small primary"
                label="Import from Odoo"
                disabled={!jobId || !erp.data.connected}
                title="Import applicants from Odoo?"
                message="New or changed CVs are downloaded and screened like an upload. Nothing is written to Odoo."
                confirmLabel="Import"
                onConfirm={importFromOdoo}
              />
            </div>
          </div>
          {showErp && jobId && <ErpPreview jobId={jobId} />}
        </div>
      )}
      {fit.data && bc && (
        <div className="card">
          <div className="row between">
            <div>
              <h3>
                Offer fit: published band {fmtNum(bc.band[0])}–{fmtNum(bc.band[1])} TND / month ·{" "}
                {fit.data.terms.work_mode} · {fit.data.terms.contract}
              </h3>
              <div className="muted small">
                Each candidate's own declared conditions (salary, notice, work mode, commitments) checked against the
                job's published terms. Shown beside the ranking, never inside it: the scores ignore them.
              </div>
            </div>
            <Badge tone={bc.share === null ? "neutral" : bc.share >= 0.5 ? "ok" : "warn"}>
              band covers {bc.within_band}/{bc.declared} declared in top {bc.k}
            </Badge>
          </div>
          {bc.share !== null && bc.share < 0.5 && (
            <div className="alert warn">
              Most of your shortlist expects more than the band pays. Settle the band or the expectations before the
              interviews, not after the offer.
            </div>
          )}
        </div>
      )}
      {gaps.data && gaps.data.diff.length > 0 && (
        <div className="card">
          <div className="row between">
            <div>
              <h3>Team-aware rubric: {gaps.data.team}</h3>
              <div className="muted small">
                Skills this role's team needs but nobody (gap) or only one person (single holder) holds. A proposal
                only: nothing changes until an HR manager applies it, and the change is audited.
              </div>
              <div className="muted small">
                Team-level counts only, no names · team of {gaps.data.team_size} · source: team skills roster
                (fictional demo data), current snapshot.
              </div>
              {gaps.data.team_size < 5 && (
                <div className="small text-warn" role="note">
                  Small team (under 5 people): a count of 1 can point to a specific colleague. Treat it as a staffing
                  signal, never as information about a person.
                </div>
              )}
            </div>
            {canEditRubric && (
              <button className="btn primary small" onClick={applyTeamWeights}>
                Apply suggested weights
              </button>
            )}
          </div>
          <ul className="small">
            {gaps.data.diff.map((d) => (
              <li key={d.esco_id}>
                <Badge tone={d.status === "gap" ? "danger" : "warn"}>{d.status === "gap" ? "gap" : "single holder"}</Badge>{" "}
                <strong>{d.label}</strong>: weight {d.before ?? "not in rubric"} → {d.after}{" "}
                <span className="muted">({d.reason})</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="split">
        <section className="card list-pane" aria-label="Ranking">
          <div className="row between">
            <h2>Ranking</h2>
            <label className="small muted" title="Candidates you plan to shortlist; borderline badges are computed for this cut-off">
              Shortlist size{" "}
              <input
                type="number"
                min={1}
                max={Math.max(1, n)}
                value={shortK}
                style={{ width: 52 }}
                onChange={(e) => setK(Math.max(1, Math.min(Math.max(1, n), Number(e.target.value) || 1)))}
              />
            </label>
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
          {!rows.loading && !rows.error && !rows.data?.length && (
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
                      onClick={() => setSelected(r.candidate_id)}
                      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), setSelected(r.candidate_id))}
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
                          {r.extraction === "ground_truth" && (
                            <span title="Fields from the demo's labelled data, not from a model run">
                              <Badge tone="warn">offline extraction</Badge>
                            </span>
                          )}
                          {r.hidden > 0 && <Badge tone="danger">{r.hidden} hidden</Badge>}
                          {r.flags > 0 && <Badge tone="danger">{r.flags} injection flags</Badge>}
                          {stabBy.get(r.candidate_id)?.label === "borderline" && (
                            <span
                              title={`In ${Math.round(100 * stabBy.get(r.candidate_id)!.p_top_k)}% of ${stab.data!.draws} rubric variations (weights ±${Math.round(100 * stab.data!.jitter)}%) this candidate is in the top ${stab.data!.k}; rank ranges ${stabBy.get(r.candidate_id)!.rank_p05}–${stabBy.get(r.candidate_id)!.rank_p95}. Review this decision one by one.`}
                            >
                              <Badge tone="warn">borderline · {Math.round(100 * stabBy.get(r.candidate_id)!.p_top_k)}% top {stab.data!.k}</Badge>
                            </span>
                          )}
                          {fills[r.candidate_id] && (
                            <span title="Evidenced skills the team lacks or holds in one person only">
                              <Badge tone="info">fills gap: {fills[r.candidate_id].join(", ")}</Badge>
                            </span>
                          )}
                          <FitBadge f={fit.data?.candidates[r.candidate_id]} />
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
          {selected ? (
            <div className="stack">
              {fit.data && (
                <OfferPanel
                  id={selected}
                  fit={fit.data.candidates[selected]}
                  terms={fit.data.terms}
                  canOffer={canOffer}
                  onDone={setNotice}
                />
              )}
              <CandidatePanel id={selected} />
            </div>
          ) : (
            <Empty>Select a candidate to see the evidence.</Empty>
          )}
        </section>
      </div>

      {pool.data && pool.data.candidates.length > 0 && (
        <section className="card">
          <div className="row between">
            <div>
              <h2>Talent pool: {pool.data.candidates.length} past applicant(s) match</h2>
              <div className="muted small">
                People who applied to other roles and opted in to the talent pool, re-scored with this job's rubric.
                Consent expires after {Math.round(pool.data.pool_days / 365)} years and can be withdrawn at any time;
                expired or withdrawn people never appear here.
              </div>
            </div>
            <button className="btn primary small" disabled={!invite.size || !canPool} onClick={sendInvites}>
              Draft invitations ({invite.size})
            </button>
          </div>
          <table className="table">
            <thead>
              <tr>
                <th />
                <th>Candidate</th>
                <th className="num">Score</th>
                <th>Matched skills</th>
                <th>Consent until</th>
              </tr>
            </thead>
            <tbody>
              {pool.data.candidates.map((p) => (
                <tr key={p.candidate_id}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`Invite ${p.name}`}
                      checked={invite.has(p.candidate_id)}
                      onChange={() => {
                        const next = new Set(invite);
                        next.has(p.candidate_id) ? next.delete(p.candidate_id) : next.add(p.candidate_id);
                        setInvite(next);
                      }}
                    />
                  </td>
                  <td>
                    <div>{p.name}</div>
                    <div className="muted small">
                      {p.candidate_id} · applied to {p.source_job_id}
                    </div>
                  </td>
                  <td className="num strong">{fmtNum(p.total, 1)}</td>
                  <td className="small">{p.matched_skills.join(", ") || "—"}</td>
                  <td className="small muted">{p.consent_expires_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {panel === "upload" && job && (
        <UploadCv
          jobs={jobs.data ?? []}
          jobId={job.job_id}
          onClose={() => setPanel(null)}
          onUploaded={(c) => {
            setPanel(null);
            setJobId(c.job_id);
            setSelected(c.candidate_id);
            rows.reload();
            say(
              c.hidden + c.flags
                ? `${c.name} was screened: ${c.hidden} hidden item(s) and ${c.flags} injection flag(s) were stripped before scoring.`
                : `${c.name} was screened and scored.`,
            );
          }}
        />
      )}
      {panel === "rubric" && job && (
        <RubricEditor
          jobId={job.job_id}
          onClose={() => setPanel(null)}
          onSaved={() => say(`Rubric for ${job.job_id} saved.${canRescore ? " Use Rescore to apply it to existing candidates." : ""}`)}
        />
      )}
    </>
  );
}

// ---------------------------------------------------------------- CV upload (POST /candidates, multipart)

async function checkPdf(file: File): Promise<string | null> {
  if (file.size > MAX_BYTES) return `This file is ${fmtNum(file.size / 1024 / 1024, 1)} MB; the limit is 5 MB.`;
  const head = new Uint8Array(await file.slice(0, 5).arrayBuffer());
  if (String.fromCharCode(...head) !== "%PDF-") return "This is not a PDF file.";
  try {
    const doc = await pdfjs.getDocument({ data: new Uint8Array(await file.arrayBuffer()), isEvalSupported: false }).promise;
    const pages = doc.numPages;
    await doc.destroy();
    if (pages > MAX_PAGES) return `This PDF has ${pages} pages; the limit is ${MAX_PAGES}.`;
  } catch {
    return "This PDF can't be read (damaged or password-protected).";
  }
  return null;
}

function UploadCv({ jobs, jobId, onClose, onUploaded }: {
  jobs: Job[]; jobId: string; onClose: () => void; onUploaded: (c: CandidateDetail) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [job, setJob] = useState(jobId);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);

  async function pick(f: File | undefined) {
    setError(null);
    setFile(null);
    if (!f) return;
    const problem = await checkPdf(f);
    if (problem) setError(problem);
    else setFile(f);
  }

  function drop(e: DragEvent) {
    e.preventDefault();
    setOver(false);
    void pick(e.dataTransfer.files?.[0]);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    form.append("job_id", job);
    form.append("name", name.trim());
    form.append("email", email.trim());
    try {
      onUploaded(await api<CandidateDetail>("/candidates", { form }));
    } catch (x) {
      setError(errMsg(x));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open title="Upload a CV" onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        <div
          className={`dropzone ${over ? "over" : ""} ${file ? "has-file" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={drop}
        >
          <p>{file ? <strong>{file.name}</strong> : "Drop a PDF here"}</p>
          <p className="muted small">PDF only · up to 5 MB · up to {MAX_PAGES} pages</p>
          <label className="btn small file-btn">
            Choose file
            <input type="file" accept="application/pdf,.pdf" className="visually-hidden" onChange={(e) => pick(e.target.files?.[0])} />
          </label>
        </div>
        <label>
          Job
          <select value={job} onChange={(e) => setJob(e.target.value)}>
            {jobs.map((j) => (
              <option key={j.job_id} value={j.job_id}>
                {j.job_id} · {j.title}
              </option>
            ))}
          </select>
        </label>
        <div className="grid2">
          <label>
            Candidate name
            <input value={name} maxLength={120} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label>
            Candidate email
            <input type="email" value={email} maxLength={254} onChange={(e) => setEmail(e.target.value)} required />
          </label>
        </div>
        <p className="muted small">
          The PDF is treated as hostile: hidden text is stripped and reported, and only validated fields are scored.
        </p>
        <ErrorBox error={error} />
        <div className="row end">
          <button type="button" className="btn ghost" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="btn primary" disabled={!file || busy}>
            {busy ? "Screening…" : "Upload and screen"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

// ---------------------------------------------------------------- rubric (GET / PUT /jobs/{id}/rubric)

const COMPONENTS = ["skills", "experience", "degree", "languages"] as const;
const DEGREES: DegreeLevel[] = ["none", "bac", "bts", "licence", "master", "ingenieur", "phd"];
const CEFRS: Cefr[] = ["A1", "A2", "B1", "B2", "C1", "C2", "native"];
const LANGS = ["fr", "en", "ar"] as const;

function RubricEditor({ jobId, onClose, onSaved }: { jobId: string; onClose: () => void; onSaved: () => void }) {
  const canEdit = usePermission("rubric.edit");
  const loaded = useLoad(() => api<Rubric>(`/jobs/${encodeURIComponent(jobId)}/rubric`), [jobId]);
  const [r, setR] = useState<Rubric | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setR(loaded.data), [loaded.data]);

  const compTotal = r ? COMPONENTS.reduce((s, c) => s + (r.component_weights[c] ?? 0), 0) : 0;
  const skillTotal = r ? Object.values(r.skill_weights).reduce((s, w) => s + w, 0) : 0;
  const valid = !!r && Math.round(compTotal) === 100 && skillTotal > 0;

  async function save() {
    if (!r) return;
    setError(null);
    try {
      await api<Rubric>(`/jobs/${encodeURIComponent(jobId)}/rubric`, { method: "PUT", body: r });
      onSaved();
      onClose();
    } catch (x) {
      setError(errMsg(x));
    }
  }

  return (
    <Modal
      open
      title={`Rubric · ${jobId}`}
      onClose={onClose}
      actions={
        <>
          <button className="btn ghost" onClick={onClose}>
            {canEdit ? "Cancel" : "Close"}
          </button>
          {canEdit && (
            <ConfirmButton
              className="btn primary"
              label="Save rubric"
              disabled={!valid}
              title="Save this rubric?"
              message="The change is recorded in the audit log. Existing scores change only when someone rescores."
              confirmLabel="Save"
              onConfirm={save}
            />
          )}
        </>
      }
    >
      <ErrorBox error={loaded.error || error} />
      <Loading show={loaded.loading} rows={5} />
      {r && (
        <fieldset disabled={!canEdit} className="stack rubric">
          {!canEdit && <div className="alert info">Read-only: only HR managers edit rubrics.</div>}
          <h3>Score components</h3>
          <p className={`small ${Math.round(compTotal) === 100 ? "muted" : "text-danger"}`}>
            Total {fmtNum(compTotal)} / 100{Math.round(compTotal) === 100 ? "" : " (must equal 100)"}
          </p>
          {COMPONENTS.map((c) => (
            <label key={c} className="slider-row">
              <span className="cap">{c}</span>
              <input
                type="range"
                min={0}
                max={100}
                step={5}
                value={r.component_weights[c] ?? 0}
                onChange={(e) => setR({ ...r, component_weights: { ...r.component_weights, [c]: Number(e.target.value) } })}
              />
              <span className="num">{r.component_weights[c] ?? 0}</span>
            </label>
          ))}

          <h3>Skill weights</h3>
          <p className="muted small">Relative weights; the share shows how much each skill counts inside the skills component.</p>
          {Object.entries(r.skill_weights).map(([skill, w]) => (
            <label key={skill} className="slider-row">
              <code>{skill}</code>
              <input
                type="range"
                min={0}
                max={10}
                step={1}
                value={w}
                onChange={(e) => setR({ ...r, skill_weights: { ...r.skill_weights, [skill]: Number(e.target.value) } })}
              />
              <span className="num">{skillTotal ? `${fmtNum((100 * w) / skillTotal)}%` : "—"}</span>
            </label>
          ))}

          <div className="grid2">
            <label>
              Minimum years of experience
              <input type="number" min={0} max={40} step={0.5} value={r.min_years}
                onChange={(e) => setR({ ...r, min_years: Number(e.target.value) })} />
            </label>
            <label>
              Required degree
              <select value={r.required_degree} onChange={(e) => setR({ ...r, required_degree: e.target.value as DegreeLevel })}>
                {DEGREES.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <h3>Languages</h3>
          {r.languages.map((l, i) => (
            <div key={i} className="row">
              <select aria-label="Language" value={l.iso}
                onChange={(e) => setR({ ...r, languages: r.languages.map((x, j) => (j === i ? { ...x, iso: e.target.value as typeof l.iso } : x)) })}>
                {LANGS.map((x) => (
                  <option key={x} value={x}>
                    {x}
                  </option>
                ))}
              </select>
              <select aria-label="Minimum level" value={l.min_cefr}
                onChange={(e) => setR({ ...r, languages: r.languages.map((x, j) => (j === i ? { ...x, min_cefr: e.target.value as Cefr } : x)) })}>
                {CEFRS.map((x) => (
                  <option key={x} value={x}>
                    {x}
                  </option>
                ))}
              </select>
              <button type="button" className="btn small ghost" onClick={() => setR({ ...r, languages: r.languages.filter((_, j) => j !== i) })}>
                Remove
              </button>
            </div>
          ))}
          <div>
            <button type="button" className="btn small" disabled={r.languages.length >= LANGS.length}
              onClick={() => setR({ ...r, languages: [...r.languages, { iso: LANGS.find((x) => !r.languages.some((l) => l.iso === x)) ?? "fr", min_cefr: "B2" }] })}>
              Add language
            </button>
          </div>
        </fieldset>
      )}
    </Modal>
  );
}

// ---------------------------------------------------------------- Odoo preview (GET /erp/jobs/{id}/applicants)

function ErpPreview({ jobId }: { jobId: string }) {
  const apps = useLoad(() => api<ErpApplicant[]>(`/erp/jobs/${encodeURIComponent(jobId)}/applicants`), [jobId]);
  return (
    <div className="section-gap">
      <ErrorBox error={apps.error} />
      <Loading show={apps.loading} rows={2} />
      {!apps.loading && !apps.data?.length && !apps.error && <Empty>No applicants for this job in Odoo.</Empty>}
      {!!apps.data?.length && (
        <table className="table">
          <thead>
            <tr>
              <th>Applicant</th>
              <th>Odoo stage</th>
              <th>HireGuard</th>
            </tr>
          </thead>
          <tbody>
            {apps.data.map((a) => (
              <tr key={a.applicant_id}>
                <td>
                  <div>{a.name || "(no name)"}</div>
                  <div className="muted small">{a.email}</div>
                </td>
                <td>{a.stage ?? "—"}</td>
                <td>{a.imported ? <Badge tone="ok">{a.candidate_id}</Badge> : <Badge>not imported</Badge>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- offer (fast-track)

function defaultStart(startBy: string): string {
  const soon = new Date(Date.now() + 30 * 86400_000).toISOString().slice(0, 10);
  return startBy > soon ? startBy : soon;
}

function OfferPanel({
  id,
  fit,
  terms,
  canOffer,
  onDone,
}: {
  id: string;
  fit?: OfferFit;
  terms: OfferTerms;
  canOffer: boolean;
  onDone: (msg: string) => void;
}) {
  const [lo, hi] = terms.pay_band_tnd_month;
  const [salary, setSalary] = useState(lo);
  const [start, setStart] = useState(defaultStart(terms.start_by));
  const [lang, setLang] = useState<"fr" | "en" | "ar">("fr");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setSalary(lo);
    setErr(null);
  }, [id, lo]);

  async function submit() {
    setErr(null);
    setBusy(true);
    try {
      const item = await api<ApprovalItem>(`/candidates/${encodeURIComponent(id)}/offer`, {
        body: { monthly_salary_tnd: salary, start_date: start, lang },
      });
      onDone(`Offer for ${id} drafted (${item.id}). Two other HR managers must approve it before it can be sent.`);
    } catch (e) {
      setErr(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <div className="row between">
        <h3>Offer fit</h3>
        <FitBadge f={fit} />
      </div>
      {fit?.checks.length ? (
        <ul className="small">
          {fit.checks.map((c) => (
            <li key={c.check}>
              <Badge tone={FIT_TONE[c.status]}>{c.status}</Badge> <strong>{CHECK_LABEL[c.check] ?? c.check}</strong>:{" "}
              {c.detail}
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted small">No conditions declared yet. Ask on the first call; don't guess.</p>
      )}
      {canOffer && (
        <details>
          <summary>Draft offer letter</summary>
          <div className="row">
            <label>
              Gross salary (TND / month)
              <input type="number" min={lo} max={hi} step={50} value={salary} onChange={(e) => setSalary(Number(e.target.value))} />
            </label>
            <label>
              Start date
              <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
            </label>
            <label>
              Language
              <select value={lang} onChange={(e) => setLang(e.target.value as "fr" | "en" | "ar")}>
                <option value="fr">Français</option>
                <option value="en">English</option>
                <option value="ar">العربية</option>
              </select>
            </label>
            <button className="btn primary small" disabled={busy} onClick={submit}>
              Send to approval
            </button>
          </div>
          <p className="muted small">
            HR sets the salary inside the published band ({fmtNum(lo)}–{fmtNum(hi)} TND), not from the candidate's ask:
            pay follows the role. Two other HR managers must approve before anything is sent.
          </p>
          <ErrorBox error={err} />
        </details>
      )}
    </div>
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

          <p className="muted small" role="note">
            Score <strong>{d.score?.status === "committed" ? "committed by an approver" : "proposed"}</strong>:
            computed by code from the validated fields below. No AI decides; a person approves the shortlist.
          </p>
          {d.extraction === "ground_truth" && (
            <div className="alert warn">
              Offline demo extraction: these fields come from the demo's labelled data, not from a model run.
            </div>
          )}
          {d.extraction === "none" && (
            <div className="alert warn">The model returned nothing usable for this CV: a person must review it.</div>
          )}
          {(highFindings > 0 || d.validated.injection_flags.length > 0) && (
            <div className="alert danger">
              {highFindings > 0 && (
                <>{highFindings} hidden item(s) were found and removed before the model read the CV. </>
              )}
              {d.validated.injection_flags.length > 0 && (
                <>
                  {d.validated.injection_flags.length} instruction-like passage(s) were flagged. Visible text is still
                  read by the model, which can only return typed fields that are checked against the CV.{" "}
                </>
              )}
              Flags never change the score; review the highlighted evidence before approving.{" "}
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
