import { useState } from "react";
import { api } from "../api";
import { Badge, Empty, ErrorBox, fmtDate, fmtNum, Loading, PageHeader, useLoad } from "../components/ui";
import type { KnowledgeGaps, ProcessView, TeamSkills } from "../types";

// HR Nexus (Team module). Every view is team- or stage-level: no person appears on this page.

const STAGE_LABEL: Record<string, string> = {
  received: "Received",
  shortlisted: "Shortlisted",
  invited: "Invited",
  interviewed: "Interviewed",
  offer_sent: "Offer sent",
};

export default function Team() {
  const [tab, setTab] = useState<"skills" | "process" | "gaps">("skills");
  return (
    <>
      <PageHeader
        title="Team (HR Nexus)"
        subtitle="HR and staff: declared team skills, how long hiring steps take, and where the handbook fails. Aggregates only, never individual scores."
        actions={
          <div className="seg">
            <button className={tab === "skills" ? "on" : ""} onClick={() => setTab("skills")}>
              Skills map
            </button>
            <button className={tab === "process" ? "on" : ""} onClick={() => setTab("process")}>
              HR process
            </button>
            <button className={tab === "gaps" ? "on" : ""} onClick={() => setTab("gaps")}>
              Knowledge gaps
            </button>
          </div>
        }
      />
      {tab === "skills" && <SkillsMap />}
      {tab === "process" && <Process />}
      {tab === "gaps" && <Gaps />}
    </>
  );
}

function SkillsMap() {
  const teams = useLoad(() => api<TeamSkills[]>("/team/skills"));
  return (
    <>
      <p className="muted small">
        Skills each team's work needs, counted from declared (fictional) skills profiles. Only holder counts leave the
        profile store. A gap or a single holder becomes a <em>proposed</em> rubric weight on the Candidates page; an HR
        manager decides whether to apply it.
      </p>
      <ErrorBox error={teams.error} />
      <Loading show={teams.loading} />
      <div className="grid2">
        {(teams.data ?? []).map((t) => (
          <section key={t.job_id} className="card">
            <div className="row between">
              <h3>{t.team}</h3>
              <span className="muted small">
                {t.team_size} people · hiring {t.job_id}
              </span>
            </div>
            <table className="table">
              <thead>
                <tr>
                  <th>Skill</th>
                  <th className="num">Holders</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {t.coverage.map((c) => (
                  <tr key={c.esco_id}>
                    <td>{c.label}</td>
                    <td className="num">
                      {c.holders}
                      {c.verified_holders ? <span className="muted small"> ({c.verified_holders} verified)</span> : null}
                    </td>
                    <td>
                      <Badge tone={c.status === "gap" ? "danger" : c.status === "single_holder" ? "warn" : "ok"}>
                        {c.status === "single_holder" ? "single holder" : c.status}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        ))}
      </div>
    </>
  );
}

function Process() {
  const [source, setSource] = useState<"live" | "simulation">("live");
  const view = useLoad(() => api<ProcessView>(`/team/process?source=${source}`), [source]);
  const v = view.data;
  const maxMedian = Math.max(1, ...(v?.transitions ?? []).map((t) => t.median_days ?? 0));
  return (
    <>
      <div className="row between">
        <p className="muted small">
          Stage times per candidate file, read from the hash-chained audit log, reported per stage only. This measures
          the process, not the people doing it.
        </p>
        <div className="seg">
          <button className={source === "live" ? "on" : ""} onClick={() => setSource("live")}>
            Live audit log
          </button>
          <button className={source === "simulation" ? "on" : ""} onClick={() => setSource("simulation")}>
            Simulation
          </button>
        </div>
      </div>
      <ErrorBox error={view.error} />
      <Loading show={view.loading} />
      {v?.source === "simulation" && (
        <div className="alert warn">
          {v.status === "not_run"
            ? "No simulation yet: run python eval/process_sim.py."
            : `${v.label} Generated ${fmtDate(v.generated_at)}.`}
        </div>
      )}
      {v && v.status !== "not_run" && v.files !== undefined && (
        <>
          {v.source === "live" && (v.time_to_offer?.n ?? 0) < 3 && (
            <div className="alert">
              Too little history in this database for stable figures ({v.files} files, {v.time_to_offer?.n ?? 0} offers).
              A fresh demo has no past; see the labelled simulation for what the panel reports.
            </div>
          )}
          <div className="tiles">
            <div className="tile">
              <div className="muted small">Candidate files</div>
              <div className="tile-value">{fmtNum(v.files)}</div>
              <div className="muted small">{v.closed ?? 0} closed</div>
            </div>
            <div className="tile accent">
              <div className="muted small">Time to offer (median)</div>
              <div className="tile-value">
                {v.time_to_offer?.median_days != null ? `${fmtNum(v.time_to_offer.median_days, 1)} d` : "—"}
              </div>
              <div className="muted small">
                n = {v.time_to_offer?.n ?? 0}
                {v.time_to_offer?.p95_days != null ? ` · p95 ${fmtNum(v.time_to_offer.p95_days, 1)} d` : ""}
              </div>
            </div>
            <div className="tile">
              <div className="muted small">Bottleneck step</div>
              <div className="tile-value small">
                {v.bottleneck ? `${STAGE_LABEL[v.bottleneck.from]} → ${STAGE_LABEL[v.bottleneck.to]}` : "—"}
              </div>
              <div className="muted small">
                {v.bottleneck ? `median ${fmtNum(v.bottleneck.median_days, 1)} d, n = ${v.bottleneck.n}` : "needs 3+ files per step"}
              </div>
            </div>
            <div className="tile">
              <div className="muted small">In progress now</div>
              <div className="tile-value">{fmtNum(v.littles_law?.observed_in_progress ?? 0)}</div>
              <div className="muted small">
                {v.littles_law
                  ? `Little's law expects ${fmtNum(v.littles_law.expected_in_progress, 1)} (${fmtNum(v.littles_law.arrivals_per_day, 2)}/day × ${fmtNum(v.littles_law.mean_days_in_pipeline, 1)} d)`
                  : ""}
              </div>
            </div>
          </div>
          <section className="card">
            <h3>Median days per step</h3>
            {(v.transitions ?? []).map((t) => (
              <div key={t.from} className="hbar-row">
                <span className="small">
                  {STAGE_LABEL[t.from]} → {STAGE_LABEL[t.to]}
                </span>
                <div
                  className="hbar"
                  title={t.n ? `n = ${t.n} files · median ${t.median_days} d · p95 ${t.p95_days} d` : "no file has made this step yet"}
                >
                  <div style={{ width: `${(100 * (t.median_days ?? 0)) / maxMedian}%` }} />
                  <span>
                    {t.n ? `${fmtNum(t.median_days, 1)} d (p95 ${fmtNum(t.p95_days, 1)} d, n = ${t.n})` : "no data yet"}
                  </span>
                </div>
              </div>
            ))}
            <div className="muted small">
              Waiting now: {Object.entries(v.wip ?? {}).map(([s, n]) => `${STAGE_LABEL[s]} ${n}`).join(" · ")}
            </div>
          </section>
        </>
      )}
    </>
  );
}

function Gaps() {
  const g = useLoad(() => api<KnowledgeGaps>("/team/knowledge-gaps"));
  const d = g.data;
  const max = Math.max(1, ...(d?.sections ?? []).map((s) => s.count ?? 0));
  return (
    <>
      <p className="muted small">
        What employees ask the Answer Desk, by handbook section, since {d?.since_week ?? "…"}. Only the matched section and
        the week are logged, never the question or the person. Counts under {d?.k ?? 5} are hidden so a rare question
        can't point at someone.
      </p>
      <ErrorBox error={g.error} />
      <Loading show={g.loading} />
      {d && d.questions === 0 && <Empty>No questions logged yet.</Empty>}
      {d && d.questions !== 0 && (
        <div className="grid2">
          <section className="card">
            <h3>Questions per handbook section</h3>
            {d.sections.map((s) => (
              <div key={s.section} className="hbar-row">
                <span className="small">{s.section}</span>
                <div className="hbar">
                  <div style={{ width: `${(100 * (s.count ?? 0)) / max}%` }} />
                  <span>{s.suppressed ? `fewer than ${d.k} (hidden)` : fmtNum(s.count ?? 0)}</span>
                </div>
              </div>
            ))}
          </section>
          <section className="card">
            <h3>No match: forwarded to HR</h3>
            <div className="tile-value">
              {d.no_match.share != null ? `${fmtNum(100 * d.no_match.share, 0)}%` : "—"}
            </div>
            <p className="muted small">
              {d.no_match.count != null
                ? `${d.no_match.count} of ${d.questions ?? "?"} questions matched no section: the handbook is missing these topics.`
                : `Fewer than ${d.k} unmatched questions (hidden).`}
            </p>
            <table className="table">
              <thead>
                <tr>
                  <th>Week</th>
                  <th className="num">Questions</th>
                  <th className="num">No match</th>
                </tr>
              </thead>
              <tbody>
                {d.weeks.map((w) => (
                  <tr key={w.week}>
                    <td>{w.week}</td>
                    <td className="num">{w.questions ?? `< ${d.k}`}</td>
                    <td className="num">
                      {w.no_match_share != null ? `${fmtNum(100 * w.no_match_share, 0)}%` : w.no_match === 0 ? "0" : `< ${d.k}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </div>
      )}
    </>
  );
}
