# Ahmed - system design, architecture, and workflow

## Mission

Own the end-to-end system design and keep HireGuard and HR Nexus coherent as
modules of one responsible HR platform without weakening their data boundaries.
Coordinate integration and the eventual `mnasri` to `main` merge. Do not merge
until the team has passed the pre-merge gate in [README.md](./README.md).

## Start here (31 Oct hand-off)

Done: [hireguard/docs/architecture.md](../hireguard/docs/architecture.md)
(system context, modules, data classes and boundaries, AI-vs-code table,
workflows, full permissions and audit matrix, refuse-to-build list, risk
register R1-R14, interface change log, release readiness, references).

- [x] R5: reverted `8f829d8` on `main` (`932747e`); tracked-file scan clean.
- [x] R4 decided: aggregate `/reviewer/stats` by batch size and week (Rayen implements).
- [x] Release gate: `backend/tests/test_release_gate.py` proves session, CSRF
      and the role matrix on every route (mutation-checked).
- [x] Pitch claims checked against `eval/results/*.json`; hook rewritten (R13).
- [x] Final pitch draft: timed 5:00 script, demo runbook, Q&A sheet in
      `hireguard/docs/pitch.md`.
- [ ] Business TBDs: run 3+ calls with
      [hireguard/docs/hr_interview_guide.md](../hireguard/docs/hr_interview_guide.md),
      then fill the pitch and `MINUTES_PER_UNIT` in `scoring/money.py`.
- [ ] Choose the ask (pilots, GPU credits or incubation).
- [ ] Keep the risk register current as owners close R1-R14; record retest evidence.
- [ ] Collect sign-offs on the interface change log (architecture §9).

## Work to execute

### Architecture and product boundaries

- [ ] Write and maintain the system context: users, modules, external services,
      trust boundaries, and deployment assumptions.
- [ ] Define how HireGuard and HR Nexus fit the employee lifecycle, and state
      what is shared versus module-specific.
- [ ] Keep candidate PII and hiring decisions separate from employee/team
      analytics. Prohibit using candidate records to infer internal employee
      characteristics, and prohibit individual stress/productivity risk scores.
- [ ] Define data ownership, retention/deletion expectations, and which roles
      can access each data class.
- [ ] Set the HR Nexus aggregation rule (k >= 5) and identify where it is
      enforced, not merely where it is described.

### Workflows and contracts

- [ ] Own the end-to-end HireGuard flow: intake -> sanitize -> model extraction
      -> validate -> score -> human review -> approved action -> audit.
- [ ] Own the HR Nexus flow: approved data source -> minimization ->
      team-level aggregation -> caveated analysis -> human interpretation.
- [ ] Define which steps may use AI and which must be deterministic code.
- [ ] Coordinate API/schema ownership and record interface changes and
      consumer sign-off.
- [ ] Ensure every state-changing action has explicit authorization, approval
      requirements, failure behavior, and an audit event.

### Security and integration leadership

- [ ] Maintain the threat model and security risk register with owners and
      retest evidence.
- [ ] Review authorization boundaries, model isolation, data retention, audit
      integrity, and the frontend/backend trust boundary with all owners.
- [ ] Run integration reviews and unblock conflicts between parallel work.
- [ ] Ensure demo claims match measured behavior and clearly label synthetic,
      oracle-mode, or otherwise limited evidence.

### Merge coordination

- [ ] Compare `mnasri` against `main` and review the full merge base and diff
      with the team.
- [ ] Check for secrets, local environment files, generated datasets, PDFs,
      `node_modules`, build directories, and machine-specific artifacts.
- [ ] Collect owner sign-offs from Hedhili, Rayen, and Yasmina.
- [ ] Confirm tests, security checks, docs, and demo all pass the pre-merge
      gate; ask the team for explicit go/no-go before merging.

## Deliverables

- A reviewed architecture and data-flow description.
- A module boundary and permissions matrix.
- A documented end-to-end workflow for each module.
- A security risk register with owner, severity, status, and retest evidence.
- A written merge readiness decision and list of known limitations.

## Definition of done

The team can explain the two modules as one platform, show that their sensitive
data and decision paths remain separated, trace each consequential action to a
human approval and audit record, and agree on a tested, reviewed merge plan.
