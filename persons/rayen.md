# Rayen - backend, scoring, and evaluation integration

## Mission

Own dependable backend behavior for the platform: stable APIs, typed contracts,
validated scoring paths, persistence, and automated backend tests. Implement
security controls in code rather than relying on frontend restrictions or
documentation.

## Left to do (1 Nov)

Done since 31 Oct: the permission matrix, lockout, idle timeout, user admin, audit of sign-in,
sign-out and account changes (closes R10), the permission-driven UI and the Odoo connector.

- [ ] **P0** Scorer: weight a skill whose `support == "listed_only"` at 0.3 or less of a
      `dated_experience` one (request R3 in [archive/person1.md](archive/person1.md)); add a twin-style test.
- [ ] **P0** N8 (`hireguard/P4_NOTES.md`): `GET /approvals` lists pending items only, so an
      approved routine item vanishes before anyone executes it. Return approved-not-executed too.
- [ ] **P0** Document in `contracts/API.md`: `GET /erp/status`, `GET /erp/jobs/{id}/applicants`,
      `POST /erp/jobs/{id}/import`, `POST /jobs/{id}/candidates/{id}/status`.
- [ ] **P1** R4: `GET /reviewer/stats` still groups by user; return hits and misses by batch
      size and week instead (decided by Ahmed).
- [ ] **P1** R12: one `scores.rescore` audit event in `POST /jobs/{id}/rescore`.
- [ ] **P1** R14: offer approver count as a setting (default 2 others; SME: 1 other).
- [ ] **P1** N10: `hidden_high` count in `list_candidates`, so a clean Arabic CV shows no badge.
- [ ] Keep `tests/test_release_gate.py` `MATRIX` and architecture §6 in step with every route.

## Work to execute

### Contracts and backend

- [ ] Review API schemas and compare the documented routes with the implemented
      routes and frontend consumers.
- [ ] Own backend changes to candidate intake, validation handoffs, scoring,
      approval workflows, and evaluation endpoints.
- [ ] Keep scoring deterministic and limited to validated, job-relevant fields.
- [ ] Ensure rubric changes and proposed scores have the correct status,
      authorization, audit event, and failure behavior.
- [ ] Keep HireGuard persistence and HR Nexus analytics data separated by
      ownership and access policy; do not join records without an approved
      purpose and documented boundary.
- [ ] Return explicit errors for unavailable dependencies, invalid input,
      authorization failures, and evaluation failures. Do not disguise errors
      as successful empty responses.

### Security implementation

- [ ] Enforce authentication, role checks, object-level authorization, and CSRF
      protection on the server for every relevant route.
- [ ] Validate file type, size, page count, request size, identifiers, and
      schema constraints server-side.
- [ ] Ensure unapproved or rejected actions cannot execute, and verify
      multi-approver rules cannot be bypassed.
- [ ] Ensure audit records cover approvals, refusals, rubric changes, and
      state-changing actions; preserve atomicity where required.
- [ ] Add regression tests for IDOR, role bypass, invalid state transitions,
      hostile input, and audit integrity.

### Evaluation and handoffs

- [ ] Integrate Hedhili's model only through the agreed typed interface and
      deterministic validator.
- [ ] Add backend contract tests for the UI workflows owned by Yasmina.
- [ ] Report evaluation results with explicit mode, sample counts, uncertainty,
      and limitations; distinguish model evaluation from oracle/code-path tests.
- [ ] Update API documentation and generated schemas whenever behavior changes.
- [ ] Provide fixture data and a stable local run/test command to the team.

## Security responsibility

Security is a backend acceptance criterion. Never accept a client-side role,
approval status, score, or candidate ownership claim as authoritative. Every
state-changing route must verify permissions and current server-side state.
Escalate any architecture conflict to Ahmed before introducing a data flow.

## Deliverables

- Contract-aligned backend routes and schemas.
- Automated backend tests for normal, invalid, and unauthorized paths.
- Reproducible evaluation integration and results.
- Updated API documentation and a list of known backend limitations.

## Definition of done

The backend tests prove role and object-level boundaries, malformed or
unvalidated model output cannot affect scoring, and no consequential action can
execute without the required human approval and audit record.
