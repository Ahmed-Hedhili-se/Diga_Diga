# Team assignments and execution plan

This folder assigns the work for Ahmed, Rayen, Hedhili, and Yasmina. Each person
owns the deliverables in their individual file and reports blockers at the next
team sync.

## Shared product direction

Build one responsible HR platform with two clearly separated modules:

1. **HireGuard** supports candidate intake, evidence-backed extraction, rubric
   scoring, and human-approved hiring workflow.
2. **HR Nexus** (the Team module) supports HR's work with staff: team skills
   coverage, HR process metrics from the audit log, the employee Answer Desk and
   its knowledge-gap radar, and self-service documents. It measures processes,
   declared skills and handbook coverage, never people. Stress, wellbeing and
   performance analytics are out of scope; an anonymous pulse survey (k >= 5) is
   a roadmap slide only.

The modules may share platform-level identity, audit, security, and deployment
standards. They must not silently combine candidate hiring records with employee
analytics. Only two cross-module flows exist, both aggregate and documented in
[hireguard/docs/architecture.md](../hireguard/docs/architecture.md) §3: team skill
holder counts become a *proposed* rubric, and per-stage hiring durations feed the
HR process panel. HR Nexus must not expose individual employee stress, productivity,
or risk scores. Its output is team-level and suppresses small groups (k >= 5).

## Status (1 Nov, `main` has every branch merged)

`main` now contains all the work from `mnasri`, `yasmina`, `hedhili` and `Rayen`. Work on a short
branch off `main` (`git checkout -b <you>-<task> origin/main`) and merge back the same day; the
old personal branches are history.

- **Health:** 449 backend tests, 11 frontend tests, the frontend build and the release gate
  (all 67 routes) pass; a full demo seed works and the audit chain verifies. After pulling, run
  `npm ci` in `hireguard/frontend` (new dev dependencies), or the build fails.
- **Headline evidence (real Qwen3-8B, same 40 attacks):** a naive screener's score moved on
  13/40, HireGuard's on 3/40. Paired, 11 attacks beat only the naive screener and 1 only
  HireGuard: exact McNemar p = 0.006.
- **Known weakness:** through the model, 26/90 twin CVs changed score (14/20 when only the CV
  language changed). Masking was added afterwards and is **not measured yet**.
- **CV extraction is slow on the measured setup:** about 40 seconds per CV. The demo uses seeded
  candidates; don't upload a CV live through the model.
- Risk register: [hireguard/docs/architecture.md](../hireguard/docs/architecture.md) §8.

Code comments still say P1-P4 (the first plan). Map them to owners:

| Label in code | Area | Owner now |
|---|---|---|
| P1 | `backend/app/pipeline/` (sanitizer, detector, extractor, validator, Answer Desk) | Hedhili (model, detector, Answer Desk), Rayen (API) |
| P2 | `backend/app/scoring/`, `eval/` | Rayen (code), Hedhili (model-mode evaluation) |
| P3 | `backend/app/workflow/` (approvals, executor, audit, email gate, follow-ups) | Rayen, Hedhili (follow-ups, pentest) |
| P4 | `frontend/`, `backend/app/auth/`, `security.py` | Yasmina (frontend), Rayen (auth backend) |
| — | `backend/app/team/` (HR Nexus), `odoo/`, `infra/` | Rayen (code), Yasmina (pages), Hedhili (Modal) |

### Left to do (P0 = before the pitch)

| Person | P0 | P1 |
|---|---|---|
| Hedhili | Re-run the model evaluation with masking on (twins, attacks, extraction on 50+ CVs); record where the model ran | Fix the attack generator (`render.py`, R1 in `archive/person1.md`) and re-count detection; re-measure the detector |
| Rayen | Earlier P0 items done. Optional: real screen recordings as a live-demo backup ([rayen.md](./rayen.md)) | Done: R4, R12, R14, N10 |
| Yasmina | Rehearse the single demo script; check the 3-minute demo video ([`hireguard/docs/demo_video/`](../hireguard/docs/demo_video/), video in `out/`, built from the dashboard); check the Evaluation tab and the follow-up screen after today's fixes | Phone and screen-reader pass; `/api/docs` off in production; Y5 copy once Ahmed decides |
| Ahmed | HR interview calls for the business numbers; choose the ask; final pitch numbers after Hedhili's run. The business numbers and the ask go into `FILL_IN` in `hireguard/docs/demo_video/build_slides.py` | Decide Y5 and R4; collect sign-offs; keep the risk register current |

## Ownership at a glance

| Person | Primary ownership | Cross-cutting responsibility |
|---|---|---|
| Ahmed | System design, architecture, end-to-end workflows, integration and merge coordination | Security architecture, privacy boundaries, final release gates |
| Hedhili | AI model selection, GPU-backed setup, model testing and evaluation | Adversarial model testing and evidence for any model-related claim |
| Rayen | Backend APIs, data contracts, scoring/evaluation integration, persistence | Server-side authorization, validation, auditability, backend security tests |
| Yasmina | Frontend, user workflows, accessibility and demo experience | Browser-side security, role-aware UX, frontend security and error-state tests |

Individual assignments and acceptance criteria are in [ahmed.md](./ahmed.md),
[rayen.md](./rayen.md), [hedhili.md](./hedhili.md), and
[yasmina.md](./yasmina.md).

## Execution order and handoffs

### 1. Agree on the system boundaries

- Ahmed publishes the module/data-flow map, role matrix, workflow, and security
  boundaries.
- Rayen checks that API and persistence boundaries can enforce them.
- Yasmina checks that the UI communicates proposed decisions and team-level
  aggregates without exposing restricted data.
- Hedhili confirms the model interface is isolated from consequential actions.

### 2. Freeze interfaces before parallel implementation

- Agree on typed request/response schemas and error behavior.
- Define the model output schema and validator contract before tuning prompts.
- Define approval and audit semantics before wiring UI actions.
- Record any contract change and notify the people consuming that interface.

### 3. Implement in parallel with explicit handoffs

- Hedhili provides tested model behavior and reproducible evaluation outputs to
  Rayen; the model proposes typed fields only.
- Rayen provides stable APIs, authorization rules, and representative fixtures
  to Yasmina.
- Yasmina returns integration failures and UX/security gaps to Rayen and Ahmed.
- Ahmed resolves architectural conflicts and keeps both modules within the
  approved privacy and authority boundaries.

### 4. Integrate and validate

- Run backend, frontend, model, privacy, security, and end-to-end checks.
- Verify docs, API schemas, generated artifacts, and the demo describe the same
  behavior.
- Record unmeasured model results as unmeasured; do not turn oracle-mode or
  synthetic results into claims about real-world model performance.

## Security is a release requirement

Security is shared ownership, not a final phase:

- **Ahmed:** threat model, trust boundaries, data-flow review, least-privilege
  role design, privacy and merge/release sign-off.
- **Hedhili:** prompt-injection, hostile-document, model-output, and model
  isolation testing.
- **Rayen:** server-side authorization, input validation, approval enforcement,
  secure persistence, audit integrity, and backend tests.
- **Yasmina:** XSS-safe rendering, session/CSRF UX, secure file handling,
  permissions in the UI, and frontend tests.

Any person who finds a security issue records it with reproduction steps,
severity, affected boundary, owner, and retest result. Critical or high-severity
issues block merge/release until fixed or explicitly accepted by the team.

## Pre-merge gate: mnasri to main

The assignments are intended to be completed before merging `mnasri` into
`main`. Do **not** merge as part of this assignment. Ahmed coordinates the
eventual merge only after the team reviews and approves it.

- [ ] Confirm the target commit and branch ancestry; review the complete diff.
- [ ] Resolve the canonical product scope and ensure the two modules' data
      boundaries are documented and enforced.
- [ ] Freeze and validate API/schema contracts against implementation and UI.
- [ ] Run backend and frontend tests, model evaluation, and security checks;
      attach results and identify any tests that could not be run.
- [ ] `main` already breaks the next item: commit `8f829d8` added `node_modules`,
      `frontend/dist` and about 380 generated PDFs. Revert it first (risk R5).
- [ ] Confirm no secrets, local databases, virtual environments, `node_modules`,
      build output, temporary files, or unintended generated datasets are
      included in the merge.
- [ ] Review threat model and close or explicitly accept all high/critical
      findings.
- [ ] Reconcile README, evaluation report, pitch, and actual demo behavior.
- [ ] Have each owner review their changed surfaces; Ahmed records final
      go/no-go.

## Team working agreement

- Keep changes in the assigned module unless the owner agrees to the change.
- Communicate API, schema, role, or data-flow changes before depending on them.
- Prefer small, reviewable commits and never commit credentials or personal
  data.
- Make human approval explicit for consequential actions; an AI model never
  sends, books, releases, or commits a decision.
- Raise uncertainty early. A clearly stated limitation is better than an
  unsupported claim.
