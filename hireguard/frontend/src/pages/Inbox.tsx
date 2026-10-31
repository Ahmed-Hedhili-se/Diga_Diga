import { api } from "../api";
import { Badge, Empty, ErrorBox, fmtDate, Loading, PageHeader, useLoad } from "../components/ui";
import type { InboxItem, InboxView } from "../types";

const LANES: { key: keyof InboxView["lanes"]; title: string; hint: string; tone: "neutral" | "warn" | "danger" }[] = [
  { key: "routine", title: "Routine", hint: "Drafts prepared from templates, waiting in the approval queue.", tone: "neutral" },
  { key: "needs_human", title: "Needs human", hint: "Rules could not classify these safely.", tone: "warn" },
  { key: "suspicious", title: "Suspicious", hint: "Failed SPF/DKIM/DMARC or the sender does not match. No candidate data is offered.", tone: "danger" },
];

const URGENCY_ORDER = { high: 0, normal: 1, low: 2 } as const;

export default function Inbox() {
  const view = useLoad(() => api<InboxView>("/inbox"));

  return (
    <>
      <PageHeader
        title="Inbox digest"
        subtitle="Grouped by type and urgency. The model labels intent; code decides the lane."
        actions={<button className="btn ghost" onClick={view.reload}>Refresh</button>}
      />
      <ErrorBox error={view.error} />
      <Loading show={view.loading} />
      {view.data && (
        <div className="lanes">
          {LANES.map((l) => {
            const items = view.data!.lanes[l.key] ?? [];
            return (
              <section key={l.key} className={`card lane lane-${l.key}`}>
                <div className="row between">
                  <h2>{l.title}</h2>
                  <Badge tone={l.tone}>{items.length}</Badge>
                </div>
                <p className="muted small">{l.hint}</p>
                {!items.length && <Empty>Nothing here.</Empty>}
                {groupByIntent(items).map(([intent, group]) => (
                  <div key={intent} className="intent-group">
                    <div className="intent-title">{intent.replace(/_/g, " ")}</div>
                    {group.map((m) => (
                      <MailRow key={m.id} m={m} />
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

function groupByIntent(items: InboxItem[]): [string, InboxItem[]][] {
  const g = new Map<string, InboxItem[]>();
  for (const m of items) {
    const k = m.intent ?? "other";
    g.set(k, [...(g.get(k) ?? []), m]);
  }
  for (const list of g.values())
    list.sort((a, b) => (URGENCY_ORDER[a.urgency ?? "normal"] ?? 1) - (URGENCY_ORDER[b.urgency ?? "normal"] ?? 1));
  return [...g.entries()];
}

function MailRow({ m }: { m: InboxItem }) {
  const auth = m.auth ?? {};
  const fail = (v?: string) => !!v && v.toLowerCase() !== "pass";
  return (
    <div className="mail">
      <div className="row between">
        <span className="strong ellipsis">{m.from ?? m.sender ?? "unknown sender"}</span>
        {m.urgency && <Badge tone={m.urgency === "high" ? "danger" : m.urgency === "low" ? "neutral" : "info"}>{m.urgency}</Badge>}
      </div>
      {m.subject && <div className="ellipsis">{m.subject}</div>}
      <div className="muted small">
        {m.id} · {fmtDate(m.received_at)}
        {m.candidate_id ? ` · ${m.candidate_id}` : ""}
      </div>
      <div className="badges">
        {(["spf", "dkim", "dmarc"] as const).map((k) =>
          auth[k] ? (
            <Badge key={k} tone={fail(auth[k]) ? "danger" : "ok"}>
              {k.toUpperCase()} {auth[k]}
            </Badge>
          ) : null,
        )}
        {(m.reasons ?? []).map((r) => (
          <Badge key={r} tone="warn">
            {r}
          </Badge>
        ))}
      </div>
    </div>
  );
}
