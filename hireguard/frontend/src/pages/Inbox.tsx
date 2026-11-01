import { ReactNode, useState } from "react";
import { Link } from "react-router-dom";
import { api, errMsg } from "../api";
import { usePermission } from "../auth";
import ChipList, { type Chip } from "../components/ChipList";
import { Badge, ConfirmButton, Empty, ErrorBox, fmtDate, Loading, PageHeader, useLoad } from "../components/ui";
import { emailIntent, emailReason, inboxStatus, reasonTone, urgencyLabel } from "../lib/labels";
import type { ApprovalItem, InboxItem, InboxView } from "../types";

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
                      {emailIntent(g.intent)}
                      {urgencyLabel(g.urgency) ? ` · ${urgencyLabel(g.urgency)}` : ""}
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

/** One "Verified sender" check when every sender check passed; red chips only for the checks that failed. */
function mailChips(m: InboxItem, fail: (v?: string) => boolean): Chip[] {
  const checks = (["spf", "dkim", "dmarc"] as const).filter((k) => m.auth?.[k]);
  const failed = checks.filter((k) => fail(m.auth![k]));
  const chips: Chip[] = failed.map((k) => ({ key: k, label: `${k.toUpperCase()} ${m.auth![k]}`, tone: "danger" as const }));
  if (checks.length === 3 && !failed.length) chips.push({ key: "verified", label: "Verified sender", tone: "ok" });
  for (const r of m.reasons) {
    if (/^dmarc_/.test(r) && failed.includes("dmarc")) continue; // the failed DMARC chip already says it
    chips.push({ key: r, label: emailReason(r), tone: reasonTone(r) });
  }
  if (m.draft_item_ids.length) chips.push({ key: "drafts", label: `${m.draft_item_ids.length} draft(s) in approvals`, tone: "info" });
  return chips;
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
        {fmtDate(m.received_at)} · {inboxStatus(m.status)}
        {m.candidate_id ? <> · <span className="mono-id">{m.candidate_id}</span></> : null} · <span className="mono-id">{m.id}</span>
      </div>
      <div className="badges">
        <ChipList chips={mailChips(m, fail)} />
      </div>
      {action}
    </div>
  );
}
