import { FormEvent, useState } from "react";
import { api, errMsg } from "../api";
import { ErrorBox, PageHeader } from "../components/ui";
import type { AnswerResult } from "../types";

export default function AnswerDesk() {
  const [q, setQ] = useState("");
  const [res, setRes] = useState<AnswerResult | null>(null);
  const [asked, setAsked] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function ask(e: FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setRes(await api<AnswerResult>("/answer-desk/ask", { body: { question: q.trim() } }));
      setAsked(q.trim());
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="HR Answer Desk"
        subtitle="Answers are exact extracts from the employee handbook, with citations. Nothing is generated."
      />
      <form className="card stack" onSubmit={ask}>
        <label>
          Your question
          <textarea
            rows={3}
            maxLength={500}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="e.g. How many days of annual leave do I get?"
          />
        </label>
        <div className="row between">
          <span className="muted small">Personal questions (your salary, your contract) go to the HR team.</span>
          <button className="btn primary" disabled={busy || !q.trim()}>
            {busy ? "Searching…" : "Ask"}
          </button>
        </div>
      </form>
      <ErrorBox error={error} />
      {res && (
        <div className="card">
          <div className="muted small">Question: {asked}</div>
          {res.kind === "routed" ? (
            <div className="alert info">
              This looks like a personal question, so it was routed to the HR queue instead of being answered
              automatically. Ticket <strong>{res.ticket_id}</strong>.
            </div>
          ) : res.extracts?.length ? (
            <div className="stack">
              {res.extracts.map((x, i) => (
                <blockquote key={i} className="extract">
                  <p>{x.text}</p>
                  <footer className="muted small">
                    Handbook · {x.section} · page {x.page}
                  </footer>
                </blockquote>
              ))}
            </div>
          ) : (
            <div className="alert warn">No matching handbook section. Try rephrasing, or ask HR directly.</div>
          )}
        </div>
      )}
    </>
  );
}
