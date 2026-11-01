import { useState } from "react";
import { Link } from "react-router-dom";
import { api, errMsg } from "../api";
import type { AgentPlan } from "../types";
import { Badge, ErrorBox, Loading } from "./ui";

// "Plan my day": the propose-only planning agent (POST /agent/plan). It reads counts through read-only tools and
// suggests where to look first. It sends, approves and changes nothing; every link opens a page where a person acts.

const TOOL_LABEL: Record<string, string> = { approvals: "Approvals", inbox: "Inbox", silent_candidates: "Silent candidates" };

export default function PlanCard() {
  const [plan, setPlan] = useState<AgentPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      setPlan(await api<AgentPlan>("/agent/plan", { method: "POST" }));
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card plan-card" aria-labelledby="ov-plan" aria-busy={busy}>
      <div className="row between">
        <h2 id="ov-plan">Today&apos;s plan</h2>
        <button className="btn primary" onClick={run} disabled={busy}>
          {plan ? "Plan again" : "Plan my day"}
        </button>
      </div>
      <p className="muted">
        A read-only agent looks at your queues and suggests where to start. It cannot send, approve or change anything.
      </p>
      <ErrorBox error={error} />
      <Loading show={busy} rows={3} />
      {plan && !busy && (
        <>
          {plan.items.length === 0 ? (
            <p>Nothing is waiting for you right now.</p>
          ) : (
            <ol className="plan-list">
              {plan.items.map((it) => (
                <li key={it.id}>
                  <Link to={it.target} className="plan-title">{it.title}</Link>
                  <span className="muted">{it.why}</span>
                </li>
              ))}
            </ol>
          )}
          <div className="row plan-meta">
            <Badge tone={plan.mode === "model" ? "info" : "neutral"}>{plan.mode === "model" ? "AI chose the steps" : "Built by rules"}</Badge>
            <span className="muted small">
              Looked at: {plan.steps.map((s) => TOOL_LABEL[s.tool] ?? s.tool).join(", ") || "nothing"} · read-only · logged in the audit trail
            </span>
          </div>
          {plan.note && <p className="muted small">{plan.note}</p>}
        </>
      )}
    </section>
  );
}
