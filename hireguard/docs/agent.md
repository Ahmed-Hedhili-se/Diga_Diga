# Planning agent ("Today's plan")

An agent for the HR team's morning: it looks at the queues and says where to start. It is **propose-only**. It follows the
same rule as the rest of the product: **the AI reads, code decides, humans approve**.

`POST /api/agent/plan` (recruiter, HR manager) · code: `backend/app/agent/` · UI: Overview → *Today's plan* · tests: `backend/tests/test_agent.py`.

## What it does

1. **Observe.** It calls read-only tools from a fixed allowlist: `approvals` (counts by risk and kind), `inbox` (counts by lane and urgency),
   `silent_candidates` (how many candidates have not answered for 3+ days). A user can only use tools their role may use.
2. **Choose.** With a reachable model, Qwen3-8B picks the next tool (or `finish`) as an enum value in a JSON schema. At most 6 tool steps and
   6 model calls per run. The model also orders the suggested steps, again as enum ids; unknown or repeated ids are dropped.
3. **Propose.** Each suggested step is a **template** filled with integers ("Review 3 high-risk approvals") plus a link to the page where a person acts.
4. **Log.** One `agent_plan` entry in the hash-chained audit log: mode, tools used, model calls, step ids.

Without a reachable model, or if the model answers badly or fails midway, the same plan is built by rules and the card says so ("Built by rules").
The feature never depends on the AI.

## What it cannot do (and the test that proves it)

| Property | How it is enforced |
|---|---|
| Cannot send, approve, execute or release | The package imports no executor, approval-creation, decision or mail code; `test_the_agent_package_cannot_act` parses its code and fails on any such name |
| Creates no approval item | `test_the_agent_creates_no_approval_item_and_writes_one_audit_entry` counts approval rows before and after |
| Cannot call a tool outside the allowlist | The model's answer is an enum; anything else is rejected and rules finish the plan (`test_a_tool_outside_the_allowlist_is_never_run`) |
| Step and call caps | `MAX_STEPS = 6`, `MAX_MODEL_CALLS = 6` (`test_step_cap_is_enforced`) |
| Text written by strangers never reaches the model | Tools return only counts, enums and system ids. A test plants a hostile instruction in approval titles and checks that it appears in no prompt and no response |
| Authorised like everything else | Permission `agent.plan` (recruiter, HR manager); admin and employee get 403; CSRF required; the route matrix test and the release gate cover it |

## Honest limits

- It is a **planner, not an autonomous worker**: it proposes where to look; a person opens the page and acts, and the normal approval rules apply.
- It sees counts, not content. It cannot say *which* email is urgent, only that urgent ones exist.
- With the 8B model the choice of tool order is a light decision; the safety does not depend on it being good. The rules fallback is the baseline.
- Not measured: how often the model's ordering differs from the rule order, or whether users prefer it. Do not claim either.

## Why this shape

A tool-using agent is the attack surface an HR system should fear: whatever it reads can steer what it does. This one reads only
numbers we computed, has no write tools, and its output is validated enums. That keeps the golden rule while giving the team a
multi-step, tool-using assistant with an audit trail.
