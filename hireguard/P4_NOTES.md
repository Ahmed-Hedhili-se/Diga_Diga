# P4 notes for the team (auth, RBAC, web security, UI)

Branch `Rayen`, synced with `yasmina` (P1, P2, P3 work). Backend: 373 pass, 1 environment-dependent failure (section 4). Live end-to-end check (33 steps, every role): all pass. Frontend: `tsc` and `vite build` pass.

## 1. Proposed changes in other layers (not applied: your code, your call)

The matrix test already proves your current `require_roles(...)` guards match `auth/permissions.py`. Switching to
`require_permission(...)` makes the intent readable and puts the permission name in the audit log:

| Layer | File | Today | Proposed |
|---|---|---|---|
| P1 | `pipeline/routes.py` | `RM`, `MA`, `EM` | `require_permission(P.candidates_read / candidates_upload / security_center_read / answer_desk_ask)` |
| P2 | `scoring/routes.py` | `RM`, `M`, `MA` | `scores_read`, `rubric_edit`, `scores_rescore`, `shortlist_propose`, `money_read`, `money_edit`, `security_center_read` |
| P3 | `workflow/routes.py` | `require_roles(R, M)` etc. | one permission per route, see `ROUTE_PERMISSIONS` |

When you add a route, add it to `ROUTE_PERMISSIONS` too: `test_route_table_and_matrix_cover_each_other` fails otherwise.

## 2. Open items

| # | For | Item |
|---|---|---|
| N1 | P1 | Done: `POST /answer-desk/ask` is live and the page renders `extract`, `routed` and `ask_hr` (R2). A 501 is still handled in case the route is switched off. |
| N2 | P2 | `eval/results/summary.json` in the repo has every section `skipped` (it was generated when `app.pipeline.service` was not importable). Re-run `python eval/harness.py` so the Evaluation tab shows real numbers. |
| N3 | all | "A recruiter only acts on candidates of jobs they can access": there is no recruiter-to-job assignment yet, so every recruiter sees every job. Needs a `job_assignments` table owned by P2; the guard would then 404 on other jobs. |
| N4 | P4 | TOTP second factor for HR managers and admins (stdlib `hmac` + base32, RFC 6238, hashed recovery codes): not done yet, next step. |
| N5 | ops | Rate-limit and lockout counters are per process. Behind a reverse proxy set `HG_TRUSTED_PROXIES` (done: pentest O2). |
| N6 | P3 | `GET /employee-questions/{id}` has no UI on purpose: the list already returns the full text. |
| N7 | P3 | H7 done on the UI side: after a booking runs, the page lists the slots the executor withdrew (`result.withdrawn`) as "withdrawn, because another slot was booked", and a 409 on a withdrawn slot says the same instead of a plain error. |
| N8 | **P3** | `GET /approvals` lists pending items only, so an approved **routine** item (email, interview slot) disappears before anyone executes it. The UI keeps approved items in a "ready to execute" list built from the decision responses (ids only, per browser session). Please add `GET /approvals?status=approved` (same role filter as the queue) so the list survives a new browser. |
| N9 | P1 | Done by P1 (`c52ed43`): the clean-candidate test counts only high-severity findings. |
| N10 | P1 | `CandidateRow.hidden` counts low-severity findings too, so the ranking badge can say "1 hidden" for a clean Arabic CV. A `hidden_high` count in `list_candidates` would let the list match the detail panel, which already separates them. |

## 3. Decisions to know

- **Lockout is invisible** (pentest F5 / H9): a locked account answers `401 "Invalid email or password"`, exactly like a wrong password. The P4 brief asked for a lockout message with the remaining time; that would tell an attacker which emails exist, so the countdown is only shown for the per-IP block (`429` + `Retry-After`), which reveals nothing about accounts. The login page states the rule ("paused 15 minutes after 5 failed attempts").
- **IP lockout threshold is 20, not 5** (`HG_LOGIN_IP_MAX_FAILED`): Tunisian call centers put hundreds of agents behind one NAT address.
- **Password reset generates the password** (shown once to the admin) instead of letting the admin type a weak one.
- **Swagger UI** stays on in dev; `HG_API_DOCS=0` removes `/api/docs` and `/api/openapi.json` in production (pentest O1).
- **Inbox page fixed**: it expected a flat list per lane while `/inbox` returns `{intent, urgency, count, items[]}` groups.

## 4. Test environment note

`test_pentest_p3.py::test_hostile_ids_give_404_not_500[traversal]` fails only when `frontend/dist` exists: the test
client collapses `/api/documents/../../etc/passwd/download` to `/etc/passwd/download`, which is outside `/api`, so the
SPA fallback serves `index.html` (200). No file outside `dist` can be served (`is_relative_to` check). With no build
folder the whole suite passes. Suggested fix for P3: accept 200 when the body is the SPA `index.html`, or build the
test app without the static fallback.
