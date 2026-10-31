import { useState } from "react";
import { Link } from "react-router-dom";
import { api, errMsg } from "../api";
import { Badge, ConfirmButton, Empty, ErrorBox, fmtDate, Loading, PageHeader, useLoad } from "../components/ui";
import type { ApprovalItem, EmployeeQuestion } from "../types";

const TEMPLATES = [
  ["received", "We received it, someone will answer personally"],
  ["contact_hr", "Personal question: please contact HR directly"],
  ["use_documents", "Request the document from the Documents page"],
] as const;

const LANGS = [
  ["fr", "Français"],
  ["en", "English"],
  ["ar", "العربية"],
] as const;

const STATUS_TONE = { open: "warn", reply_drafted: "info", answered: "ok" } as const;

export default function EmployeeQuestions() {
  const qs = useLoad(() => api<EmployeeQuestion[]>("/employee-questions"));
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const open = (qs.data ?? []).filter((q) => q.status === "open").length;

  return (
    <>
      <PageHeader
        title="Employee questions"
        subtitle="Personal questions routed from the Answer Desk. Replies are fixed templates and go through approval."
        actions={<Badge tone={open ? "warn" : "ok"}>{open} open</Badge>}
      />
      <ErrorBox error={qs.error || error} />
      {notice && (
        <div className="alert ok">
          {notice} <Link to="/approvals">Open the approval queue</Link>
        </div>
      )}
      <Loading show={qs.loading} />
      {!qs.loading && !qs.error && !qs.data?.length && <Empty>No employee questions yet. They appear here when an employee asks HR.</Empty>}
      <div className="stack">
        {(qs.data ?? []).map((q) => (
          <QuestionCard
            key={q.id}
            q={q}
            onDrafted={(item) => {
              setError(null);
              setNotice(`Reply drafted as approval item ${item.id}. It is sent only after approval.`);
              qs.reload();
            }}
            onError={(e) => setError(e)}
          />
        ))}
      </div>
    </>
  );
}

function QuestionCard({ q, onDrafted, onError }: {
  q: EmployeeQuestion; onDrafted: (i: ApprovalItem) => void; onError: (e: string) => void;
}) {
  const [template, setTemplate] = useState<string>(TEMPLATES[0][0]);
  const [lang, setLang] = useState<string>("fr");

  async function draft() {
    try {
      onDrafted(await api<ApprovalItem>(`/employee-questions/${encodeURIComponent(q.id)}/reply`, { body: { template, lang } }));
    } catch (x) {
      onError(errMsg(x));
    }
  }

  return (
    <article className="card">
      <div className="row between">
        <div className="badges">
          <Badge tone="info">{q.topic}</Badge>
          <Badge tone={STATUS_TONE[q.status]}>{q.status.replace("_", " ")}</Badge>
          <Badge tone={q.risk >= 40 ? "warn" : "neutral"}>risk {q.risk}</Badge>
        </div>
        <span className="muted small">
          {q.id} · {fmtDate(q.created_at)}
        </span>
      </div>
      {/* employee-written text: rendered as text, never as HTML */}
      <p className="question-text">{q.text}</p>
      {q.status === "open" ? (
        <div className="row">
          <label className="grow">
            Reply template
            <select value={template} onChange={(e) => setTemplate(e.target.value)}>
              {TEMPLATES.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </label>
          <label>
            Language
            <select value={lang} onChange={(e) => setLang(e.target.value)}>
              {LANGS.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </label>
          <ConfirmButton
            className="btn primary align-end"
            label="Draft reply"
            title="Draft this reply?"
            message="The reply is prepared from the template and added to the approval queue. Nothing is sent until it is approved."
            confirmLabel="Draft reply"
            onConfirm={draft}
          />
        </div>
      ) : (
        q.reply_item_id && <div className="muted small">Reply item: {q.reply_item_id}</div>
      )}
    </article>
  );
}
