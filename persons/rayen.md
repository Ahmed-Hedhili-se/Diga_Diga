# Rayen - backend, scoring, and evaluation integration

## Mission

Own dependable backend behavior for the platform: stable APIs, typed contracts,
validated scoring paths, persistence, and automated backend tests. Implement
security controls in code rather than relying on frontend restrictions or
documentation.

## Start here (31 Oct hand-off)

New backend surfaces to review and own (tests in `backend/tests/test_fast_track.py`
and `test_team.py`; contracts in `hireguard/contracts/API.md`):
`scoring/offer_fit.py`, `scoring/rediscover.py`, `workflow/followups.py`,
`team/` (skills, process metrics, knowledge gaps), optional condition and consent
fields on `POST /candidates`.

- [ ] R3 (P0): implement `POST /answer-desk/ask` (now 501). Retrieval only over
      `data/handbook/` sections, return the cited passage word for word, "no match"
      routes to HR; call `team.knowledge_gaps.record(section_or_None, lang)`. Never
      store the question text.
- [ ] R10 (P1, about 30 min): audit `auth.login` (success and failure, no password),
      `auth.logout` and `auth.user_create` (with the role) in `auth/routes.py`.
- [ ] R4 (decided by Ahmed: aggregate): `GET /reviewer/stats` returns canary hits and
      misses by batch size and week, never by user id; keep roles M A; test it.
- [ ] R14: make the offer approval count a per-customer setting (default 2 other HR
      managers; SME: 1). Today the demo can't clear an offer with 2 HR accounts.
- [ ] R12: one `scores.rescore` audit event in `POST /jobs/{id}/rescore`.
- [ ] R6: rename scorecard criterion `team_fit` to `collaboration` (contract change:
      tell Yasmina, update `API.md`).
- [ ] Sign off the interface change log in `hireguard/docs/architecture.md` §9.
- [ ] Run `backend/.venv/Scripts/python.exe -m pytest -q` before every push (107 pass
      now). `tests/test_release_gate.py` fails on any new or changed route until its
      roles are added to `MATRIX` there and to architecture §6, on purpose.

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
