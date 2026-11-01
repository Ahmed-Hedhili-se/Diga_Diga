# Yasmina - frontend, user workflows, and browser security

## Mission

Own the user-facing workflows for HireGuard and the HR Nexus research/demo
surfaces. Make the interface clear about what is proposed, what is approved,
what is measured, and what is only a team-level signal.

## Left to do (1 Nov)

Done since 31 Oct: the frontend security review (6 findings, retested), honest error and empty
states, the UI-to-API contract test, offer-fit and talent-pool screens, mode labels on the
Evaluation tab, and the demo script with a backup path.

- [ ] **P0** Rehearse the demo twice with the single script (`hireguard/docs/demo_script.md`)
      inside 5:00, and record the backup video of the same path. Use seeded candidates only:
      a live upload through the model takes about 40 seconds.
- [ ] **P0** After today's fixes: check the Evaluation tab (code-path and model runs, each
      labelled) and the single follow-up screen.
- [x] **P0** The offer beat stops at "1 of 2 approvals" with two HR accounts (risk R14):
      present it as the control working. Done: the Approvals page explains the wait, and an HR manager can set the rule to 1.
- [ ] **P1** Phone-width pass and screen-reader pass on the review and approval flows.
- [x] **P1** Production: `HG_API_DOCS=0` so `/api/docs` and its relaxed CSP are off. The backend now logs a warning when secure cookies are on and docs are still on.
- [ ] **P1** Y5 wording on the skills map once Ahmed decides.

## Work to execute

### Product workflows and UI

- [ ] Build and maintain role-aware navigation and the intended user journeys.
- [ ] Make candidate evidence, score components, hidden-text findings, and
      approval status understandable without implying that an AI made the final
      decision.
- [ ] Present HR Nexus only as team-level organizational analysis, with sample
      size, time window, provenance, uncertainty, and caveats where relevant.
- [ ] Ensure dashboards do not expose person-level employee stress,
      productivity, or risk scores.
- [ ] Keep UI types and API behavior aligned with Rayen's contracts.
- [ ] Provide helpful empty, loading, permission-denied, and error states;
      request failures must not look like “no data.”
- [ ] Test responsive behavior and accessibility for essential review and
      approval flows.

### Browser security

- [ ] Render all candidate- or employee-derived text as text, never executable
      HTML; review every rich-text or PDF display path.
- [ ] Validate upload behavior in the UI while treating backend validation as
      authoritative.
- [ ] Verify session, logout, CSRF-token, and permission-denied behavior with
      the backend; do not treat hidden navigation as access control.
- [ ] Review PDF/document previews, download behavior, CSP assumptions, and
      third-party browser dependencies.
- [ ] Add tests for hostile text rendering, role-gated controls, error states,
      and approval confirmation.
- [ ] Report frontend security findings to Ahmed and Rayen with reproduction
      steps and retest results.

### Integration and demo

- [ ] Run the end-to-end flow against the current backend contract.
- [ ] Keep demo data fictional and clearly label synthetic or simulated
      outcomes.
- [ ] Ensure UI copy matches the measured evaluation results and documented
      known limits.
- [ ] Rehearse the demo and prepare a backup path for unavailable GPU/model
      services without presenting fallback output as a live model result.

## Security responsibility

The browser is not a trusted enforcement layer. Never imply that a hidden button,
route, or client-side check protects data. Escalate any API response that
contains fields beyond the user's role or the agreed contract.

## Deliverables

- Working role-appropriate pages for the agreed demo scope.
- UI-to-API integration tests and a record of unresolved errors.
- Frontend security review checklist and retested fixes.
- Demo script that accurately represents the running system.

## Definition of done

Users can complete the agreed workflows, understand human approval and
uncertainty, and cannot use the interface to reveal restricted data or execute
an action that the backend has not authorized.
