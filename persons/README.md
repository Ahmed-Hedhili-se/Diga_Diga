# Team assignments and execution plan

This folder assigns the work for Ahmed, Rayen, Hedhili, and Yasmina. Each person
owns the deliverables in their individual file and reports blockers at the next
team sync.

## Shared product direction

Build one responsible HR platform with two clearly separated modules:

1. **HireGuard** supports candidate intake, evidence-backed extraction, rubric
   scoring, and human-approved hiring workflow.
2. **HR Nexus** explores team-level coordination and organizational-health
   analytics using privacy-preserving aggregates.

The modules may share platform-level identity, audit, security, and deployment
standards. They must not silently combine candidate hiring records with employee
analytics. HR Nexus must not expose individual employee stress, productivity,
or risk scores. Its output is team-level and suppresses small groups (k >= 5).

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
