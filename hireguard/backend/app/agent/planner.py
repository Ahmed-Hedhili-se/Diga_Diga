"""The planning loop. The model only chooses (a) which allowlisted tool to call next and (b) the order of suggested
steps, both as enum values we validate. Titles and reasons are fixed templates filled with integers.
Without a reachable model the same plan is built by rules ("rules" mode), so the feature never depends on the AI.
"""
from __future__ import annotations

import json
import logging

from ..contracts import UserOut
from ..pipeline import llm
from ..workflow import audit
from ..workflow.common import new_id
from . import tools

log = logging.getLogger("hireguard.agent")

MAX_STEPS = 6          # tool calls per run, whatever the model says
MAX_MODEL_CALLS = 6    # model calls per run (tool choices + one ordering)

SYSTEM_TOOLS = (
    "You help an HR team plan their day. You may only choose which read-only tool to call next, or 'finish'. "
    "Tools return counts only. Answer with JSON that matches the schema. Never write anything else."
)
SYSTEM_ORDER = (
    "You order a fixed list of suggested next steps for an HR team, most urgent first. "
    "Answer with JSON that matches the schema: an array of the given step ids, each used at most once."
)


def _candidates(obs: dict) -> list[dict]:
    """Suggested steps, built by code from observed counts. Titles are templates; targets are app pages."""
    out: list[dict] = []
    a, i, s = obs.get("approvals"), obs.get("inbox"), obs.get("silent_candidates")
    if a and a["high_risk"]:
        n = a["high_risk"]
        out.append({"id": "review_high_risk", "priority": 90, "target": "/approvals",
                    "title": f"Review {n} high-risk approval{'s' if n != 1 else ''}",
                    "why": "Offers, documents and held mail are decided one by one, and offers need a second approver."})
    if i and i["urgent_needs_human"]:
        n = i["urgent_needs_human"]
        out.append({"id": "answer_urgent_mail", "priority": 80, "target": "/inbox",
                    "title": f"Read {n} urgent email{'s' if n != 1 else ''} that need a person",
                    "why": "The inbox gate could not handle these safely on its own."})
    if i and i["suspicious"]:
        n = i["suspicious"]
        out.append({"id": "check_suspicious_mail", "priority": 70, "target": "/inbox",
                    "title": f"Look at {n} held email{'s' if n != 1 else ''} that failed sender checks",
                    "why": "They are held and show no candidate data. Check the sender before anyone lets them through."})
    if a and a["routine"]:
        n = a["routine"]
        out.append({"id": "review_routine", "priority": 50, "target": "/approvals",
                    "title": f"Review {n} routine approval{'s' if n != 1 else ''}, one batch at a time",
                    "why": "Drafts are waiting. Nothing is sent until you approve."})
    if s and s["count"]:
        n = s["count"]
        out.append({"id": "follow_up_silent", "priority": 40, "target": "/approvals",
                    "title": f"{n} candidate{'s' if n != 1 else ''} silent for {s['days']}+ days",
                    "why": "Reminder drafts can be prepared; they go to the approval queue first."})
    return out


def _choose_tool(remaining: list[str], obs: dict, budget: dict) -> str | None:
    if budget["model_calls"] >= MAX_MODEL_CALLS:
        return None
    budget["model_calls"] += 1
    schema = {"type": "object", "properties": {"tool": {"type": "string", "enum": remaining + ["finish"]}},
              "required": ["tool"], "additionalProperties": False}
    user_msg = json.dumps({"already_observed": obs, "tools_left": remaining}, sort_keys=True)
    out = llm.complete_json(SYSTEM_TOOLS, user_msg, schema)
    name = out.get("tool") if isinstance(out, dict) else None
    if name == "finish" or name in remaining:
        return name
    raise ValueError("model chose a tool outside the allowlist")     # caller falls back to rules


def _order(cands: list[dict], budget: dict) -> list[str] | None:
    if len(cands) < 2 or budget["model_calls"] >= MAX_MODEL_CALLS:
        return None
    budget["model_calls"] += 1
    ids = [c["id"] for c in cands]
    schema = {"type": "object", "properties": {"order": {"type": "array", "items": {"type": "string", "enum": ids}}},
              "required": ["order"], "additionalProperties": False}
    user_msg = json.dumps({"steps": [{"id": c["id"], "title": c["title"]} for c in cands]}, sort_keys=True)
    out = llm.complete_json(SYSTEM_ORDER, user_msg, schema)
    order = out.get("order") if isinstance(out, dict) else None
    if not isinstance(order, list):
        return None
    seen: list[str] = []
    for x in order:
        if x in ids and x not in seen:
            seen.append(x)
    return seen or None


def _model_ready() -> bool:
    try:
        st = llm.status()
        return bool(st.get("reachable") and st.get("model_loaded"))
    except Exception:      # status must never break the plan
        return False


def run(user: UserOut) -> dict:
    run_id = new_id("PLAN")
    allowed = tools.allowed_tools(user)
    obs: dict[str, dict] = {}
    steps: list[dict] = []
    budget = {"model_calls": 0}
    mode = "rules"
    note = None

    if allowed and _model_ready():
        mode = "model"
        remaining = list(allowed)
        try:
            while remaining and len(steps) < MAX_STEPS:
                name = _choose_tool(remaining, obs, budget)
                if name is None or name == "finish":
                    break
                obs[name] = tools.call(name, user)
                steps.append({"tool": name, "by": "model"})
                remaining.remove(name)
        except Exception as e:         # LLMUnavailable, bad JSON, anything: fall back, never fail the page
            log.warning("agent model step failed (%s): continuing by rules", type(e).__name__)
            mode, note = "rules", "The model could not be used for every step; rules finished the plan."
    elif allowed:
        note = "AI model not reachable: this plan was built by rules."

    for name in allowed:                # rules mode, or what a failed model run did not reach
        if name not in obs and mode == "rules" and len(steps) < MAX_STEPS:
            obs[name] = tools.call(name, user)
            steps.append({"tool": name, "by": "rules"})

    cands = sorted(_candidates(obs), key=lambda c: -c["priority"])
    if mode == "model":
        try:
            order = _order(cands, budget)
            if order:
                rank = {cid: n for n, cid in enumerate(order)}
                cands.sort(key=lambda c: (rank.get(c["id"], len(rank)), -c["priority"]))
        except Exception as e:
            log.warning("agent ordering failed (%s): kept rule order", type(e).__name__)
            note = "The model could not order the steps; rule order used."

    items = [{"rank": n + 1, "id": c["id"], "title": c["title"], "why": c["why"], "target": c["target"],
              "needs_approval": True} for n, c in enumerate(cands)]
    audit.append(user.id, "agent_plan", "agent_run", run_id,
                 {"mode": mode, "tools": [s["tool"] for s in steps], "model_calls": budget["model_calls"],
                  "items": [i["id"] for i in items]})
    return {"run_id": run_id, "mode": mode, "note": note, "steps": steps, "items": items,
            "limits": {"max_steps": MAX_STEPS, "read_only": True, "executes_nothing": True}}
