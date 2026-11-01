import { Fragment, KeyboardEvent, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, errMsg } from "../api";
import { useAuth, usePermission } from "../auth";
import { Badge, ConfirmButton, Empty, ErrorBox, fmtDate, Loading, PageHeader, plain, useLoad } from "../components/ui";
import type {
  ApprovalItem, ApprovalsView, AttentionStats, EmployeeQuestion, InterviewReminder, SilentCandidate,
} from "../types";

const KIND_LABEL: Record<string, string> = {
  email_send: "Emails to send",
  interview_booking: "Interview bookings",
  status_change: "Status changes",
  shortlist_commit: "Shortlist commits",
  document_release: "Document releases",
  held_email_release: "Held emails",
  leave_request: "Leave requests",
  offer: "Offers",
};

/** What we keep about an approved item between page loads: enough to run it, no payload (no personal data). */
interface ReadyItem {
  id: string;
  kind: string;
  title: string;
}

/**
 * GET /approvals lists pending items only, so an approved routine item would vanish before anyone runs it.
 * Decision responses carry the new status: approved items are kept here (per user, per browser session) until
 * executed. P4_NOTES N8 asks P3 for a server-side list.
 */
function useReadyList(userId: string | undefined) {
  const key = `hg.ready.${userId ?? "anon"}`;
  const [items, setItems] = useState<ReadyItem[]>(() => {
    try {
      return JSON.parse(sessionStorage.getItem(key) ?? "[]") as ReadyItem[];
    } catch {
      return [];
    }
  });
  useEffect(() => {
    try {
      sessionStorage.setItem(key, JSON.stringify(items));
    } catch {
      /* storage unavailable: the list just lasts for this page */
    }
  }, [key, items]);
  const track = useCallback((updated: ApprovalItem[]) => {
    setItems((cur) => {
      const byId = new Map(cur.map((i) => [i.id, i]));
      for (const u of updated) {
        if (u.status === "approved") byId.set(u.id, { id: u.id, kind: u.kind, title: u.title });
        else byId.delete(u.id);
      }
      return [...byId.values()];
    });
  }, []);
  const drop = useCallback((ids: string[]) => setItems((cur) => cur.filter((i) => !ids.includes(i.id))), []);
  return { items, track, drop };
}

/** A withdrawn interview slot answers 409 "item is rejected": say why, so nobody thinks a colleague rejected it. */
function decisionError(e: unknown, kind: string): string {
  if (kind === "interview_booking" && e instanceof ApiError && e.status === 409 && e.message.includes("rejected")) {
    return "This slot was withdrawn: another slot was booked for the same candidate. Refresh the queue.";
  }
  return errMsg(e);
}

export default function Approvals() {
  const { user } = useAuth();
  const view = useLoad(() => api<ApprovalsView>("/approvals"));
  const attention = useLoad(() => api<AttentionStats>("/approvals/attention"));
  const [msg, setMsg] = useState<{ tone: "ok" | "danger"; text: string } | null>(null);
  const canFollowups = usePermission("followups.manage");
  const canExecute = usePermission("approvals.execute");
  const ready = useReadyList(user?.id);

  const report = (tone: "ok" | "danger", text: string) => {
    setMsg({ tone, text });
    view.reload();
    attention.reload();
  };
  const att = attention.data;

  const batches = view.data?.batches.filter((b) => b.items.length) ?? [];
  const high = view.data?.high_risk ?? [];

  return (
    <>
      <PageHeader
        title="Approval queue"
        subtitle="Nothing is sent, booked, released or recorded until a human approves it here."
        actions={<button className="btn ghost" onClick={view.reload}>Refresh</button>}
      />
      <ErrorBox error={view.error} />
      {msg && (
        <div className={`alert ${msg.tone}`} role="status">
          {msg.text}
        </div>
      )}
      <Counters high={high.length} routine={batches.reduce((n, b) => n + b.items.length, 0)} loading={view.loading} />
      <Loading show={view.loading} />
      {att && (
        <div className={`alert ${att.max_batch_size < att.default_max_batch_size ? "warn" : "info"}`}>
          {att.max_batch_size < att.default_max_batch_size
            ? `Attention guard: ${att.recent.missed} of the last ${att.recent.canaries} planted test items were approved. `
              + `Routine batches are capped at ${att.max_batch_size} item(s) until reviews are careful again.`
            : `Attention guard: routine batches hold at most ${att.max_batch_size} items. Planted test items `
              + `check that each batch is really read (${att.recent.missed}/${att.recent.canaries} recent misses).`}
        </div>
      )}

      {canExecute && ready.items.length > 0 && (
        <>
          <h2 className="section-title">
            Approved, ready to execute <Badge tone="ok">{ready.items.length}</Badge>
          </h2>
          <section className="card">
            <table className="table">
              <tbody>
                {ready.items.map((it) => (
                  <tr key={it.id}>
                    <td>
                      <div>{it.title}</div>
                      <div className="muted small">
                        {KIND_LABEL[it.kind] ?? it.kind} · {it.id}
                      </div>
                    </td>
                    <td className="num">
                      <div className="row end">
                        <button className="btn small ghost" onClick={() => ready.drop([it.id])}>
                          Hide
                        </button>
                        <ExecuteButton item={{ id: it.id, status: "approved" }} report={report} onGone={ready.drop} />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}

      <h2 className="section-title">
        High-risk items <Badge tone="danger">{high.length}</Badge>
      </h2>
      {high.length ? (
        <HighRiskReviewer items={high} report={report} track={ready.track} onGone={ready.drop} />
      ) : (
        <Empty>No high-risk items waiting.</Empty>
      )}

      <h2 className="section-title">
        Routine batches <Badge>{batches.reduce((n, b) => n + b.items.length, 0)}</Badge>
      </h2>
      {!batches.length && <Empty>No routine items waiting.</Empty>}
      <div className="stack">
        {batches.map((b) => (
          <BatchCard key={`${b.batch_id}-${b.chunk ?? 0}`} batchId={b.batch_id} kind={b.kind} items={b.items}
            report={report} track={ready.track} />
        ))}
      </div>

      {canFollowups && <Followups report={report} />}
    </>
  );
}

/** HR manager home: what is waiting, at a glance. Each counter shows only if the user may act on it. */
function Counters({ high, routine, loading }: { high: number; routine: number; loading: boolean }) {
  const canQuestions = usePermission("questions.reply");
  const canReminders = usePermission("interviews.reminders");
  const questions = useLoad(
    () => (canQuestions ? api<EmployeeQuestion[]>("/employee-questions") : Promise.resolve([])),
    [canQuestions],
  );
  const reminders = useLoad(
    () => (canReminders ? api<InterviewReminder[]>("/interviews/reminders") : Promise.resolve([])),
    [canReminders],
  );
  if (loading) return null;
  const open = (questions.data ?? []).filter((q) => q.status === "open").length;
  return (
    <div className="tiles">
      <div className={`card tile ${high ? "tile-alert" : ""}`}>
        <div className="muted small">High-risk items</div>
        <div className="tile-value">{high}</div>
      </div>
      <div className="card tile">
        <div className="muted small">Routine items in batches</div>
        <div className="tile-value">{routine}</div>
      </div>
      {canQuestions && (
        <Link to="/questions" className="card tile tile-link">
          <div className="muted small">Open employee questions</div>
          <div className="tile-value">{open}</div>
        </Link>
      )}
      {canReminders && (
        <Link to="/interviews" className="card tile tile-link">
          <div className="muted small">Interviews missing a scorecard</div>
          <div className="tile-value">{reminders.data?.length ?? 0}</div>
        </Link>
      )}
    </div>
  );
}

/** Candidate follow-ups (P3): silent candidates, and reminder drafts that go through the normal queue. */
function Followups({ report }: { report: Report }) {
  const [days, setDays] = useState(3);
  const preview = useLoad(() => api<SilentCandidate[]>(`/followups/preview?days=${days}`), [days]);

  async function draft() {
    try {
      const r = await api<{ item_ids: string[] }>(`/followups/run?days=${days}`, { method: "POST" });
      report(
        "ok",
        r.item_ids.length
          ? `${r.item_ids.length} reminder(s) drafted for approval: ${r.item_ids.join(", ")}.`
          : "No reminder needed: every candidate has heard from us recently.",
      );
      preview.reload();
    } catch (e) {
      report("danger", errMsg(e));
    }
  }

  const n = preview.data?.length ?? 0;
  return (
    <section className="card section-gap">
      <div className="row between">
        <div>
          <h2>Silent candidates</h2>
          <p className="muted small">Candidates who have not heard from us. Reminders are drafted from templates and need approval.</p>
        </div>
        <div className="row">
          <label className="inline">
            Silent for at least
            <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
              {[3, 7, 14, 30].map((d) => (
                <option key={d} value={d}>
                  {d} days
                </option>
              ))}
            </select>
          </label>
          <ConfirmButton
            className="btn primary"
            label={`Draft reminders (${n})`}
            disabled={!n}
            title="Draft follow-up reminders?"
            message={`${n} reminder email(s) will be prepared and added to the approval queue. Nothing is sent until approved.`}
            confirmLabel="Draft reminders"
            onConfirm={draft}
          />
        </div>
      </div>
      <ErrorBox error={preview.error} />
      <Loading show={preview.loading} rows={2} />
      {!preview.loading && !n && <Empty>No silent candidates for this period.</Empty>}
      {!!n && (
        <table className="table">
          <tbody>
            {preview.data!.map((c) => (
              <tr key={c.candidate_id}>
                <td>{c.candidate_id}</td>
                <td className="muted small">{c.job_id}</td>
                <td className="num">
                  <Badge tone={c.days_silent > 7 ? "warn" : "neutral"}>{c.days_silent} days silent</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

type Report = (tone: "ok" | "danger", text: string) => void;
type Track = (items: ApprovalItem[]) => void;

function BatchCard({ batchId, kind, items, report, track }: {
  batchId: string; kind: string; items: ApprovalItem[]; report: Report; track: Track;
}) {
  const [checked, setChecked] = useState<Set<string>>(new Set(items.filter((i) => i.status === "pending").map((i) => i.id)));
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function decide(decision: "approve" | "reject") {
    setBusy(true);
    try {
      const out = await api<ApprovalItem[]>(`/approvals/batches/${encodeURIComponent(batchId)}/decision`, {
        body: { decision, item_ids: [...checked] },
      });
      track(out);
      report(
        "ok",
        decision === "approve"
          ? `${out.length} item(s) approved in batch ${batchId}. They are listed under "Approved, ready to execute".`
          : `${out.length} item(s) rejected in batch ${batchId}.`,
      );
    } catch (e) {
      report("danger", decisionError(e, kind));
    } finally {
      setBusy(false);
    }
  }

  const toggle = (id: string) => {
    const n = new Set(checked);
    n.has(id) ? n.delete(id) : n.add(id);
    setChecked(n);
  };

  return (
    <div className="card">
      <div className="row between">
        <div>
          <h3>{KIND_LABEL[kind] ?? kind}</h3>
          <div className="muted small">
            Batch {batchId} · {items.length} item(s)
          </div>
          {kind === "interview_booking" && (
            <div className="muted small">
              Each candidate gets several proposed slots. Booking one withdraws the others automatically: they leave
              this queue because another slot was booked, not because a colleague rejected them.
            </div>
          )}
        </div>
        <div className="row">
          <button className="btn ghost" disabled={busy || !checked.size} onClick={() => decide("reject")}>
            Reject selected
          </button>
          <button className="btn primary" disabled={busy || !checked.size} onClick={() => decide("approve")}>
            Approve selected ({checked.size})
          </button>
        </div>
      </div>
      <table className="table">
        <tbody>
          {items.map((it) => (
            <Fragment key={it.id}>
              <tr>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`Select ${it.id}`}
                    disabled={it.status !== "pending"}
                    checked={checked.has(it.id)}
                    onChange={() => toggle(it.id)}
                  />
                </td>
                <td>
                  <div>{it.title}</div>
                  <div className="muted small">
                    {it.id} · risk {it.risk} · {fmtDate(it.created_at)}
                  </div>
                </td>
                <td>
                  <StatusBadge item={it} />
                </td>
                <td className="num">
                  <button className="link" onClick={() => setOpen(open === it.id ? null : it.id)}>
                    {open === it.id ? "Hide diff" : "Diff"}
                  </button>
                </td>
              </tr>
              {open === it.id && (
                <tr>
                  <td />
                  <td colSpan={3}>
                    <DiffView item={it} />
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function HighRiskReviewer({ items, report, track, onGone }: {
  items: ApprovalItem[]; report: Report; track: Track; onGone: (ids: string[]) => void;
}) {
  const { user } = useAuth();
  const [idx, setIdx] = useState(0);
  const [busy, setBusy] = useState(false);
  const item = items[Math.min(idx, items.length - 1)];
  const approvals = item.decisions.filter((d) => d.decision === "approve");
  const iApproved = approvals.some((d) => d.user_id === user?.id);
  const needsSecond = item.required_approvals > 1 && approvals.length < item.required_approvals;

  async function decide(decision: "approve" | "reject") {
    setBusy(true);
    try {
      const updated = await api<ApprovalItem>(`/approvals/${encodeURIComponent(item.id)}/decision`, { body: { decision } });
      track([updated]);
      const left = updated.required_approvals - updated.decisions.filter((d) => d.decision === "approve").length;
      report(
        "ok",
        decision === "reject"
          ? `${item.id} rejected.`
          : left > 0
            ? `${item.id}: your approval is recorded. A second HR manager must approve.`
            : `${item.id} approved.`,
      );
    } catch (e) {
      report("danger", decisionError(e, item.kind));
    } finally {
      setBusy(false);
    }
  }

  // keyboard: ← / → (or k / j) move between items; approving stays a deliberate click or Enter on the button
  function onKey(e: KeyboardEvent<HTMLDivElement>) {
    if ((e.target as HTMLElement).closest("button, input, select, textarea, a")) return;
    if ((e.key === "ArrowRight" || e.key === "j") && idx < items.length - 1) setIdx(idx + 1);
    else if ((e.key === "ArrowLeft" || e.key === "k") && idx > 0) setIdx(idx - 1);
    else return;
    e.preventDefault();
  }

  return (
    <div
      className="card high-risk"
      tabIndex={0}
      onKeyDown={onKey}
      aria-label={`High-risk item ${Math.min(idx, items.length - 1) + 1} of ${items.length}. Use the left and right arrow keys to move between items.`}
      aria-keyshortcuts="ArrowLeft ArrowRight"
    >
      <div className="row between">
        <div>
          <div className="muted small">
            Item {Math.min(idx, items.length - 1) + 1} of {items.length}: reviewed one at a time · <kbd>←</kbd>{" "}
            <kbd>→</kbd> to move
          </div>
          <h3>{item.title}</h3>
          <div className="muted small">
            {KIND_LABEL[item.kind] ?? item.kind} · {item.id} · created by {item.created_by} · {fmtDate(item.created_at)}
          </div>
        </div>
        <div className="badges">
          <Badge tone="danger">risk {item.risk}</Badge>
          <StatusBadge item={item} />
        </div>
      </div>
      {needsSecond && (
        <div className="alert warn">
          2nd approver needed: {approvals.length} of {item.required_approvals} approvals.
          {iApproved && " You already approved; another HR manager must approve."}
        </div>
      )}
      <DiffView item={item} />
      <div className="row between">
        <div className="row">
          <button className="btn ghost small" disabled={idx === 0} onClick={() => setIdx(idx - 1)}>
            ← Previous
          </button>
          <button className="btn ghost small" disabled={idx >= items.length - 1} onClick={() => setIdx(idx + 1)}>
            Next →
          </button>
        </div>
        <div className="row">
          <ExecuteButton item={item} report={report} onGone={onGone} />
          <button className="btn ghost" disabled={busy || item.status !== "pending"} onClick={() => decide("reject")}>
            Reject
          </button>
          <button className="btn primary" disabled={busy || item.status !== "pending" || iApproved} onClick={() => decide("approve")}>
            Approve
          </button>
        </div>
      </div>
    </div>
  );
}

/** Demo moment: running an unapproved item returns HTTP 403 from the executor. */
function ExecuteButton({ item, report, onGone }: {
  item: Pick<ApprovalItem, "id" | "status">; report: Report; onGone: (ids: string[]) => void;
}) {
  const [busy, setBusy] = useState(false);
  async function run() {
    setBusy(true);
    try {
      const r = await api<{ result?: { withdrawn?: string[] } }>(`/executor/run/${encodeURIComponent(item.id)}`, { method: "POST" });
      const withdrawn = r.result?.withdrawn ?? [];
      onGone([item.id, ...withdrawn]);
      report(
        "ok",
        withdrawn.length
          ? `${item.id} executed. Withdrawn, because another slot was booked: ${withdrawn.join(", ")}.`
          : `${item.id} executed.`,
      );
    } catch (e) {
      if (e instanceof ApiError && (e.status === 404 || e.status === 409 || (e.status === 403 && item.status === "approved"))) {
        onGone([item.id]); // no longer runnable (already executed, withdrawn or gone): drop it from the ready list
      }
      if (e instanceof ApiError && e.status === 403) {
        report("danger", `403 Forbidden: the executor refused ${item.id}. ${e.message}`);
      } else report("danger", errMsg(e));
    } finally {
      setBusy(false);
    }
  }
  if (item.status === "executed" || item.status === "rejected") return null;
  return (
    <button className={`btn ${item.status === "approved" ? "primary" : "danger-outline"}`} disabled={busy} onClick={run}>
      {item.status === "approved" ? "Execute" : "Execute without approval"}
    </button>
  );
}

function StatusBadge({ item }: { item: ApprovalItem }) {
  const tone = item.status === "approved" || item.status === "executed" ? "ok" : item.status === "rejected" ? "danger" : "neutral";
  return <Badge tone={tone}>{item.status}</Badge>;
}

function DiffView({ item }: { item: ApprovalItem }) {
  const before = (item.diff?.before ?? {}) as Record<string, unknown>;
  const after = (item.diff?.after ?? item.payload ?? {}) as Record<string, unknown>;
  const keys = Array.from(new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})]));
  if (!keys.length) return <Empty>No changes to show.</Empty>;
  return (
    <table className="table diff">
      <thead>
        <tr>
          <th>Field</th>
          <th>Before</th>
          <th>After</th>
        </tr>
      </thead>
      <tbody>
        {keys.map((k) => {
          const b = plain(before?.[k]);
          const a = plain(after?.[k]);
          const changed = b !== a;
          return (
            <tr key={k} className={changed ? "changed" : ""}>
              <td>
                <code>{k}</code>
              </td>
              <td className="old">{item.diff?.before === undefined ? "" : b}</td>
              <td className="new">{a}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
