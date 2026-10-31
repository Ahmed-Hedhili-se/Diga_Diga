import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, errMsg } from "../api";
import { hasRole, useAuth } from "../auth";
import EvidenceText, { pageOfOffset } from "../components/EvidenceText";
import PdfViewer from "../components/PdfViewer";
import { Badge, Empty, ErrorBox, fmtNum, Loading, PageHeader, useLoad } from "../components/ui";
import type {
  ApprovalItem,
  CandidateDetail,
  CandidateRow,
  FitStatus,
  Job,
  OfferFit,
  OfferFitView,
  OfferTerms,
  RediscoverView,
  Span,
  StabilityView,
  TeamGapsView,
} from "../types";

interface TextView {
  visible_text: string;
  page_offsets: number[];
}

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
  const { user } = useAuth();
  const jobs = useLoad(() => api<Job[]>("/jobs"));
  const [jobId, setJobId] = useState<string>("");
  const [k, setK] = useState<number | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [shortlist, setShortlist] = useState<Set<string>>(new Set());
  const [notice, setNotice] = useState<string | null>(null);
  const [actionErr, setActionErr] = useState<string | null>(null);

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

  return (
    <>
      <PageHeader
        title="Candidates"
        subtitle="Ranked by code from validated fields only. Scores are proposals until HR commits the shortlist."
        actions={
          <select value={jobId} onChange={(e) => { setJobId(e.target.value); setSelected(null); setK(null); }}>
            {(jobs.data ?? []).map((j) => (
              <option key={j.job_id} value={j.job_id}>
                {j.job_id} · {j.title}
              </option>
            ))}
          </select>
        }
      />
      <ErrorBox error={jobs.error || rows.error || gaps.error || fit.error || pool.error || actionErr} />
      {notice && <div className="alert ok">{notice}</div>}
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
            </div>
            {hasRole(user, "hr_manager") && (
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
        <section className="card list-pane">
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
        </section>

        <section className="detail-pane">
          {selected ? (
            <div className="stack">
              {fit.data && (
                <OfferPanel
                  id={selected}
                  fit={fit.data.candidates[selected]}
                  terms={fit.data.terms}
                  canOffer={hasRole(user, "hr_manager")}
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
            <button className="btn primary small" disabled={!invite.size} onClick={sendInvites}>
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
    </>
  );
}

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
