import { Fragment, useState } from "react";
import { api, ApiError, errMsg } from "../api";
import { useAuth } from "../auth";
import { Badge, Empty, ErrorBox, fmtDate, Loading, PageHeader, plain, useLoad } from "../components/ui";
import type { ApprovalItem, ApprovalsView } from "../types";

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

export default function Approvals() {
  const view = useLoad(() => api<ApprovalsView>("/approvals"));
  const [msg, setMsg] = useState<{ tone: "ok" | "danger"; text: string } | null>(null);

  const report = (tone: "ok" | "danger", text: string) => {
    setMsg({ tone, text });
    view.reload();
  };

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
      {msg && <div className={`alert ${msg.tone}`}>{msg.text}</div>}
      <Loading show={view.loading} />

      <h2 className="section-title">
        High-risk items <Badge tone="danger">{high.length}</Badge>
      </h2>
      {high.length ? <HighRiskReviewer items={high} report={report} /> : <Empty>No high-risk items waiting.</Empty>}

      <h2 className="section-title">
        Routine batches <Badge>{batches.reduce((n, b) => n + b.items.length, 0)}</Badge>
      </h2>
      {!batches.length && <Empty>No routine items waiting.</Empty>}
      <div className="stack">
        {batches.map((b) => (
          <BatchCard key={b.batch_id} batchId={b.batch_id} kind={b.kind} items={b.items} report={report} />
        ))}
      </div>
    </>
  );
}

type Report = (tone: "ok" | "danger", text: string) => void;

function BatchCard({ batchId, kind, items, report }: { batchId: string; kind: string; items: ApprovalItem[]; report: Report }) {
  const [checked, setChecked] = useState<Set<string>>(new Set(items.filter((i) => i.status === "pending").map((i) => i.id)));
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function decide(decision: "approve" | "reject") {
    setBusy(true);
    try {
      await api(`/approvals/batches/${encodeURIComponent(batchId)}/decision`, {
        body: { decision, item_ids: [...checked] },
      });
      report("ok", `${checked.size} item(s) ${decision === "approve" ? "approved" : "rejected"} in batch ${batchId}.`);
    } catch (e) {
      report("danger", errMsg(e));
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

function HighRiskReviewer({ items, report }: { items: ApprovalItem[]; report: Report }) {
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
      report("danger", errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card high-risk">
      <div className="row between">
        <div>
          <div className="muted small">
            Item {Math.min(idx, items.length - 1) + 1} of {items.length}: reviewed one at a time
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
          <ExecuteButton item={item} report={report} />
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
function ExecuteButton({ item, report }: { item: ApprovalItem; report: Report }) {
  const [busy, setBusy] = useState(false);
  async function run() {
    setBusy(true);
    try {
      await api(`/executor/run/${encodeURIComponent(item.id)}`, { method: "POST" });
      report("ok", `${item.id} executed.`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        report("danger", `403 Forbidden: the executor refused ${item.id} because it is not approved. ${e.message}`);
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
