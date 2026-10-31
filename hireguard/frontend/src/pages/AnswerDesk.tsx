import { FormEvent, useEffect, useState } from "react";
import { api, ApiError, errMsg } from "../api";
import { usePermission } from "../auth";
import { Badge, Empty, ErrorBox, fmtDate, Loading, PageHeader, useLoad } from "../components/ui";
import type { AnswerResult, EmployeeQuestion, QuestionTopic } from "../types";

const TOPICS: [QuestionTopic, string][] = [
  ["leave", "Leave"],
  ["salary", "Salary"],
  ["certificate", "Certificate"],
  ["contract", "Contract"],
  ["other", "Other"],
];

const STATUS_LABEL = { open: "waiting for HR", reply_drafted: "reply being checked", answered: "answered" } as const;

export default function AnswerDesk() {
  const canAskHr = usePermission("questions.ask");
  const [q, setQ] = useState("");
  const [res, setRes] = useState<AnswerResult | null>(null);
  const [asked, setAsked] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [busy, setBusy] = useState(false);
  const [routedCount, setRoutedCount] = useState(0); // refreshes "My questions" after a routed ticket
  const [handoff, setHandoff] = useState<{ text: string; n: number } | null>(null); // pre-fills "Ask the HR team"

  async function ask(e: FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api<AnswerResult>("/answer-desk/ask", { body: { question: q.trim() } });
      setRes(r);
      if (r.kind === "routed") setRoutedCount((n) => n + 1);
      setAsked(q.trim());
    } catch (err) {
      if (err instanceof ApiError && err.status === 501) setUnavailable(true);
      else setError(errMsg(err));
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
          Your question about company policy
          <textarea
            rows={3}
            maxLength={1000}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="e.g. How many days of annual leave do I get?"
          />
        </label>
        <div className="row between">
          <span className="muted small">Personal questions (your salary, your contract) go to the HR team.</span>
          <button className="btn primary" disabled={busy || q.trim().length < 3}>
            {busy ? "Searching…" : "Search the handbook"}
          </button>
        </div>
      </form>
      <ErrorBox error={error} />
      {unavailable && (
        <div className="alert info">
          Handbook search isn't switched on yet.{canAskHr ? " You can still ask the HR team directly below." : ""}
        </div>
      )}
      {res && (
        <div className="card">
          <div className="muted small">Question: {asked}</div>
          {res.kind === "routed" && (
            <div className="alert info">
              This looks like a personal question, so it was sent to the HR team instead of being answered
              automatically: ticket <strong>{res.ticket_id}</strong>. You can follow it under "My questions".
            </div>
          )}
          {res.kind === "extract" && (
            <div className="stack">
              {res.extracts.map((x) => (
                <blockquote key={x.section_id} className="extract">
                  {/* exact handbook paragraph, rendered as text */}
                  <p>{x.text}</p>
                  <footer className="muted small">
                    Handbook, {x.section}, p.{x.page}
                  </footer>
                </blockquote>
              ))}
            </div>
          )}
          {res.kind === "ask_hr" && (
            <div className="alert warn">
              <p>{res.message}</p>
              {canAskHr && (
                <button className="btn small" onClick={() => setHandoff({ text: asked, n: (handoff?.n ?? 0) + 1 })}>
                  Send this question to HR
                </button>
              )}
            </div>
          )}
        </div>
      )}
      {canAskHr && <AskHr prefill={handoff} refresh={routedCount} />}
    </>
  );
}

/** POST /employee-questions + GET /employee-questions (own questions only). */
function AskHr({ prefill, refresh }: { prefill: { text: string; n: number } | null; refresh: number }) {
  const mine = useLoad(() => api<EmployeeQuestion[]>("/employee-questions"), [refresh]);
  const [topic, setTopic] = useState<QuestionTopic>("leave");
  const [text, setText] = useState("");

  useEffect(() => {
    if (!prefill) return;
    setText(prefill.text);
    setTopic("other");
    document.getElementById("ask-hr-text")?.focus();
  }, [prefill]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function send(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const t = await api<EmployeeQuestion>("/employee-questions", { body: { topic, text: text.trim() } });
      setNotice(`Sent to HR as ticket ${t.id}. You will get an answer by email once HR has checked it.`);
      setText("");
      mine.reload();
    } catch (x) {
      setError(errMsg(x));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid2 section-gap">
      <form className="card stack" onSubmit={send}>
        <h2>Ask the HR team</h2>
        <p className="muted small">Only HR managers read this. It is never sent to an AI model.</p>
        <label>
          Topic
          <select value={topic} onChange={(e) => setTopic(e.target.value as QuestionTopic)}>
            {TOPICS.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <label>
          Your question
          <textarea id="ask-hr-text" rows={4} maxLength={2000} value={text} onChange={(e) => setText(e.target.value)} required />
        </label>
        <ErrorBox error={error} />
        {notice && <div className="alert ok">{notice}</div>}
        <button className="btn primary" disabled={busy || !text.trim()}>
          {busy ? "Sending…" : "Send to HR"}
        </button>
      </form>
      <section className="card">
        <h2>My questions</h2>
        <ErrorBox error={mine.error} />
        <Loading show={mine.loading} rows={2} />
        {!mine.loading && !mine.data?.length && <Empty>You haven't asked HR anything yet.</Empty>}
        <ul className="plain-list">
          {(mine.data ?? []).map((m) => (
            <li key={m.id}>
              <div className="row between">
                <Badge tone="info">{m.topic}</Badge>
                <Badge tone={m.status === "answered" ? "ok" : "neutral"}>{STATUS_LABEL[m.status]}</Badge>
              </div>
              {m.text && <p className="question-text">{m.text}</p>}
              <div className="muted small">
                {m.id} · {fmtDate(m.created_at)}
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
