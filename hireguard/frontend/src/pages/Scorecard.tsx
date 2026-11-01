import { FormEvent, useState } from "react";
import { api, errMsg } from "../api";
import { usePermission } from "../auth";
import { Badge, Empty, ErrorBox, fmtDate, Loading, PageHeader, useLoad } from "../components/ui";
import type { InterviewReminder } from "../types";

const CRITERIA = [
  ["technical", "Technical skills", "The skills the job description asks for, shown in the answers and exercises."],
  ["problem_solving", "Problem solving", "How they broke down the problems you gave them and reached an answer."],
  ["communication", "Communication", "Whether their explanations were clear and to the point."],
  ["collaboration", "Working with others", "Examples of working with others on a task, as the job requires. Rate what they described, not whether you liked them."],
] as const;

const SCALE = [
  [1, "Weak"],
  [2, "Mixed"],
  [3, "Good"],
  [4, "Excellent"],
] as const;

const RECS = [
  ["strong_no", "Strong no"],
  ["no", "No"],
  ["yes", "Yes"],
  ["strong_yes", "Strong yes"],
] as const;

type Ratings = Partial<Record<(typeof CRITERIA)[number][0], number>>;

export default function Scorecard() {
  const [interviewId, setInterviewId] = useState("");
  const [ratings, setRatings] = useState<Ratings>({});
  const [rec, setRec] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const canReminders = usePermission("interviews.reminders");

  const complete = interviewId.trim() && rec && CRITERIA.every(([k]) => ratings[k]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api(`/interviews/${encodeURIComponent(interviewId.trim())}/scorecard`, {
        body: { ratings, recommendation: rec },
      });
      setDone(`Scorecard saved for ${interviewId.trim()}.`);
      setRatings({});
      setRec("");
    } catch (x) {
      setError(errMsg(x));
    }
  }

  return (
    <>
      <PageHeader title="Interviews" subtitle="Two-minute structured scorecards: the same criteria for every candidate." />
      {canReminders && <Reminders onPick={(id) => setInterviewId(id)} />}
      <form className="card stack scorecard" onSubmit={submit}>
        <h2>Interview scorecard</h2>
        <label>
          Interview ID
          <input value={interviewId} onChange={(e) => setInterviewId(e.target.value)} placeholder="INT-…" maxLength={40} />
        </label>
        {CRITERIA.map(([key, label, hint]) => (
          <fieldset key={key}>
            <legend>{label}</legend>
            <div className="muted small">{hint}</div>
            <div className="seg">
              {SCALE.map(([v, l]) => (
                <button
                  type="button"
                  key={v}
                  className={ratings[key] === v ? "on" : ""}
                  onClick={() => setRatings({ ...ratings, [key]: v })}
                >
                  {v} · {l}
                </button>
              ))}
            </div>
          </fieldset>
        ))}
        <fieldset>
          <legend>Recommendation</legend>
          <div className="seg">
            {RECS.map(([v, l]) => (
              <button type="button" key={v} className={rec === v ? "on" : ""} onClick={() => setRec(v)}>
                {l}
              </button>
            ))}
          </div>
        </fieldset>
        <ErrorBox error={error} />
        {done && <div className="alert ok">{done}</div>}
        <button className="btn primary" disabled={!complete}>
          Submit scorecard
        </button>
      </form>
    </>
  );
}

/** GET /interviews/reminders: interviews that ended without a scorecard. */
function Reminders({ onPick }: { onPick: (interviewId: string) => void }) {
  const r = useLoad(() => api<InterviewReminder[]>("/interviews/reminders"));
  return (
    <section className="card section-gap-bottom">
      <div className="row between">
        <h2>Missing scorecards</h2>
        <Badge tone={r.data?.length ? "warn" : "ok"}>{r.data?.length ?? 0}</Badge>
      </div>
      <ErrorBox error={r.error} />
      <Loading show={r.loading} rows={2} />
      {!r.loading && !r.error && !r.data?.length && <Empty>Every finished interview has a scorecard.</Empty>}
      {!!r.data?.length && (
        <table className="table">
          <tbody>
            {r.data.map((x) => (
              <tr key={x.interview_id}>
                <td>
                  <div>{x.candidate_id}</div>
                  <div className="muted small">
                    {x.interview_id} · interviewer {x.interviewer_id} · ended {fmtDate(x.ended_at)}
                  </div>
                </td>
                <td className="num">
                  <button className="btn small" onClick={() => onPick(x.interview_id)}>
                    Fill scorecard
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
