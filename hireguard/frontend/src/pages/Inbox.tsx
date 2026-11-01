import { ReactNode, useState } from "react";
import { Link } from "react-router-dom";
import { api, errMsg } from "../api";
import { usePermission } from "../auth";
import { Badge, ConfirmButton, Empty, ErrorBox, fmtDate, Loading, PageHeader, useLoad } from "../components/ui";
import type { ApprovalItem, FollowupsView, InboxItem, InboxView } from "../types";

const LANES: { key: keyof InboxView["lanes"]; title: string; hint: string; tone: "neutral" | "warn" | "danger" }[] = [
  { key: "routine", title: "Routine", hint: "Drafts prepared from templates, waiting in the approval queue.", tone: "neutral" },
  { key: "needs_human", title: "Needs human", hint: "Rules could not classify these safely. Handle them yourself.", tone: "warn" },
  { key: "suspicious", title: "Suspicious", hint: "Failed SPF/DKIM/DMARC or the sender does not match. Held, and no candidate data is offered.", tone: "danger" },
];

export default function Inbox() {
  const view = useLoad(() => api<InboxView>("/inbox"));
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const canRelease = usePermission("inbox.release_request");

  async function requestRelease(m: InboxItem) {
    setError(null);
    try {
      const item = await api<ApprovalItem>(`/inbox/${encodeURIComponent(m.id)}/release-request`, { method: "POST" });
      setNotice(`Release request created as approval item ${item.id}. A second check happens in the approval queue.`);
      view.reload();
    } catch (x) {
      setError(errMsg(x));
    }
  }

  return (
    <>
      <PageHeader
        title="Inbox digest"
        subtitle="Grouped by type and urgency. The model labels intent; code decides the lane."
        actions={<button className="btn ghost" onClick={view.reload}>Refresh</button>}
      />
      <ErrorBox error={view.error || error} />
      {notice && (
        <div className="alert ok">
          {notice} <Link to="/approvals">Open the approval queue</Link>
        </div>
      )}
      <Loading show={view.loading} rows={5} />
      <AwaitingReply />
      {view.data && (
        <div className="lanes">
          {LANES.map((l) => {
            const groups = view.data!.lanes[l.key] ?? [];
            const total = groups.reduce((n, g) => n + g.count, 0);
            return (
              <section key={l.key} className={`card lane lane-${l.key}`} aria-label={`${l.title} lane`}>
                <div className="row between">
                  <h2>{l.title}</h2>
                  <Badge tone={l.tone}>{total}</Badge>
                </div>
                <p className="muted small">{l.hint}</p>
                {!total && <Empty>Nothing here.</Empty>}
                {groups.map((g) => (
                  <div key={`${g.intent}-${g.urgency}`} className="intent-group">
                    <div className="intent-title">
                      {(g.intent ?? "unclassified").replace(/_/g, " ")}
                      {g.urgency && g.urgency !== "normal" ? ` · ${g.urgency}` : ""}
                    </div>
                    {g.items.map((m) => (
                      <MailRow
                        key={m.id}
                        m={m}
                        action={
                          canRelease && m.status === "held" ? (
                            <ConfirmButton
                              className="btn small"
                              label="Request release"
                              title="Request release of this held email?"
                              message="This creates a high-risk approval item. The email stays held until an HR manager approves the release."
                              confirmLabel="Create request"
                              onConfirm={() => requestRelease(m)}
                            />
                          ) : null
                        }
                      />
                    ))}
                  </div>
                ))}
              </section>
            );
          })}
        </div>
      )}
    </>
  );
}

function MailRow({ m, action }: { m: InboxItem; action: ReactNode }) {
  const fail = (v?: string) => !!v && v.toLowerCase() !== "pass";
  return (
    <div className="mail">
      <div className="row between">
        <span className="strong ellipsis" title={m.from}>
          {m.from_name || m.from}
        </span>
        {m.urgency === "high" && <Badge tone="danger">urgent</Badge>}
      </div>
      <div className="ellipsis">{m.subject}</div>
      {m.body_preview && <div className="muted small preview">{m.body_preview}</div>}
      <div className="muted small">
        {m.id} · {fmtDate(m.received_at)}
        {m.candidate_id ? ` · ${m.candidate_id}` : ""} · {m.status}
      </div>
      <div className="badges">
        {(["spf", "dkim", "dmarc"] as const).map((k) =>
          m.auth?.[k] ? (
            <Badge key={k} tone={fail(m.auth[k]) ? "danger" : "ok"}>
              {k.toUpperCase()} {m.auth[k]}
            </Badge>
          ) : null,
        )}
        {m.reasons.map((r) => (
          <Badge key={r} tone="warn">
            {r}
          </Badge>
        ))}
        {m.draft_item_ids.length > 0 && <Badge tone="info">{m.draft_item_ids.length} draft(s) in approvals</Badge>}
      </div>
      {action}
    </div>
  );
}

// ---------------------------------------------------------------- follow-ups (Ahmed)

function AwaitingReply() {
  const due = useLoad(() => api<FollowupsView>("/followups"));
  const [pick, setPick] = useState<Set<string>>(new Set());
  const [notice, setNotice] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function draft() {
    setErr(null);
    try {
      const items = await api<ApprovalItem[]>("/followups/draft", { body: { candidate_ids: [...pick] } });
      setNotice(`${items.length} reminder(s) drafted into the approval queue. Nothing is sent before approval.`);
      setPick(new Set());
      due.reload();
    } catch (e) {
      setErr(errMsg(e));
    }
  }

  const rows = due.data?.candidates ?? [];
  return (
    <section className="card">
      <div className="row between">
        <div>
          <h2>Awaiting reply</h2>
          <p className="muted small">
            Candidates we wrote to who have not answered for {due.data?.days ?? 3} business days or more. Reminders are
            drafted from a template, at most {due.data?.max_reminders ?? 2} per candidate, and wait for approval.
          </p>
        </div>
        <button className="btn primary small" disabled={!pick.size} onClick={draft}>
          Draft reminders ({pick.size})
        </button>
      </div>
      <ErrorBox error={due.error || err} />
      {notice && <div className="alert ok">{notice}</div>}
      {!due.loading && !due.error && !rows.length && <Empty>Everyone we wrote to has answered or is not due yet.</Empty>}
      {rows.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th />
              <th>Candidate</th>
              <th>Our last email</th>
              <th className="num">Business days</th>
              <th>Reminders</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.candidate_id}>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`Remind ${r.name}`}
                    disabled={!r.can_remind}
                    checked={pick.has(r.candidate_id)}
                    onChange={() => {
                      const next = new Set(pick);
                      next.has(r.candidate_id) ? next.delete(r.candidate_id) : next.add(r.candidate_id);
                      setPick(next);
                    }}
                  />
                </td>
                <td>
                  <div>{r.name}</div>
                  <div className="muted small">
                    {r.candidate_id} · {r.job_id}
                  </div>
                </td>
                <td>
                  <div className="ellipsis">{r.last_subject}</div>
                  <div className="muted small">{fmtDate(r.last_sent_at)}</div>
                </td>
                <td className="num">{r.business_days_waiting}</td>
                <td>
                  {r.reminder_pending ? (
                    <Badge tone="info">waiting for approval</Badge>
                  ) : (
                    <Badge tone={r.can_remind ? "neutral" : "warn"}>
                      {r.reminders_sent}/{due.data!.max_reminders} sent
                    </Badge>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
