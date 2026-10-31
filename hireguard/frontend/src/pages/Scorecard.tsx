import { FormEvent, useState } from "react";
import { api, errMsg } from "../api";
import { ErrorBox, PageHeader } from "../components/ui";

const CRITERIA = [
  ["technical", "Technical skills"],
  ["problem_solving", "Problem solving"],
  ["communication", "Communication"],
  ["team_fit", "Team fit"],
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
      <PageHeader title="Interview scorecard" subtitle="Two minutes, structured: same criteria for every candidate." />
      <form className="card stack scorecard" onSubmit={submit}>
        <label>
          Interview ID
          <input value={interviewId} onChange={(e) => setInterviewId(e.target.value)} placeholder="INT-…" maxLength={40} />
        </label>
        {CRITERIA.map(([key, label]) => (
          <fieldset key={key}>
            <legend>{label}</legend>
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
