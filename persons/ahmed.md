# Ahmed - system design, architecture, and workflow

## Mission

Own the end-to-end system design and keep HireGuard and HR Nexus coherent as
modules of one responsible HR platform without weakening their data boundaries.
Coordinate integration and the eventual `mnasri` to `main` merge. Do not merge
until the team has passed the pre-merge gate in [README.md](./README.md).

## Left to do (1 Nov)

Fixed on 1 Nov (with Claude, each step tested; also: the Answer Desk now feeds the knowledge-gap radar):
- [x] Evaluation tab: `GET /api/eval/summary` serves the labelled runs (code path and model)
      instead of the missing `summary.json`.
- [x] One follow-up engine instead of two (no double reminders, never to rejected candidates).
- [x] Pitch and architecture: real model numbers, the paired result, the twin caveat, honest
      wording on where the model runs, current test counts and risk statuses.
- [x] Root README for the platform; HR Nexus research moved to `research/`; one task list
      (`persons/`), older plans in `persons/archive/`; one demo script.

Yours:
- [ ] **P0** HR interview calls (3+) with
      [hireguard/docs/hr_interview_guide.md](../hireguard/docs/hr_interview_guide.md), then fill
      the business slide and `MINUTES_PER_UNIT` in `backend/app/scoring/money.py`.
- [ ] **P0** Choose the ask (pilots, GPU credits or incubation).
- [ ] **P0** After Hedhili's masked run: put the final model numbers on the metrics slide.
- [ ] **P1** Decide Y5 (`docs/frontend_security.md`): team skill counts for teams under 5 people.
- [ ] **P1** Decide R4 is implemented as agreed (reviewer stats by batch size, not by person).
- [ ] **P1** Collect sign-offs on the interface change log (architecture §9); keep §8 current.

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
