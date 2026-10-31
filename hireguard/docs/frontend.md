# Frontend, auth and web security (P4)

## Run
- Dev: `uvicorn app.main:app --port 8000` in `backend/`, then `npm run dev` in `frontend/` → http://localhost:5173 (Vite proxies `/api`).
- Prod/demo: `npm run build`; FastAPI serves `frontend/dist` from the same origin under the strict CSP → http://localhost:8000.
- Demo users: `python -m app.seed` in `backend/` prints 5 random passwords **once**. There are no default accounts.

## Pages and permissions
Menu, routes, buttons and home page come from the permissions in `GET /auth/me` (see [security_auth.md](security_auth.md)),
never from hard-coded roles. Visiting a page you can't use shows a friendly 403 page; unknown addresses show 404.
Home page: HR Manager → Approvals (with counters), Recruiter → Candidates, Employee → My documents, Admin → Users.

| Page | Permission | API |
|---|---|---|
| Candidates: ranking, score breakdown with evidence in text/PDF, CV upload (drag & drop, 5 MB / 6 pages checked in the browser), rubric editor (component weights total 100; read-only without `rubric.edit`), rescore, propose shortlist, Odoo preview/import, free interview slots | `candidates.read` (+ `candidates.upload`, `rubric.edit`, `scores.rescore`, `shortlist.propose`, `erp.import`, `calendar.read`) | `/jobs`, `/jobs/{id}/rubric`, `/jobs/{id}/rescore`, `/jobs/{id}/shortlist`, `/candidates`, `/candidates/{id}[/text,/pdf]`, `/calendar/slots`, `/erp/status`, `/erp/jobs/{id}/applicants`, `/erp/jobs/{id}/import` |
| Approvals: counters, routine batches + diff, high-risk one by one (← → keys), 2nd approver, "execute without approval" → 403, silent candidates + draft reminders | `approvals.decide` (+ `followups.manage`, `questions.reply`, `interviews.reminders` for counters) | `/approvals`, `/approvals/{id}/decision`, `/approvals/batches/{id}/decision`, `/executor/run/{id}`, `/followups/preview`, `/followups/run` |
| Inbox digest (routine / needs human / suspicious), request release of held mail | `inbox.read` (+ `inbox.release_request`) | `/inbox`, `/inbox/{id}/release-request` |
| Interviews: missing scorecards, structured scorecard | `interviews.scorecard` (+ `interviews.reminders`) | `/interviews/reminders`, `/interviews/{id}/scorecard` |
| Employee questions: read, reply with a template (→ approval item) | `questions.reply` | `/employee-questions`, `/employee-questions/{id}/reply` |
| My documents | `documents.request` | `/documents/request`, `/documents/mine`, `/documents/{id}/download` |
| Answer Desk: handbook search, ask HR, my questions | `answer_desk.ask` (+ `questions.ask`) | `/answer-desk/ask`, `/employee-questions` |
| Security Center: blocked attacks, evaluation metrics (95% CI), reviewer vigilance, audit chain + anchor now | `security_center.read` (+ `audit.read`, `audit.anchor`) | `/security/findings`, `/eval/summary`, `/reviewer/stats`, `/audit`, `/audit/verify`, `/audit/anchor` |
| Money dashboard | `money.read` (+ `money.edit`) | `/money`, `/money/settings` |
| Users: create, change role (confirmed), deactivate, unlock, reset password (shown once), last sign-in, permission matrix, ingest demo `.eml` | `users.manage` (+ `inbox.ingest`) | `/auth/users`, `/auth/users/{id}`, `/auth/users/{id}/reset-password`, `/auth/permissions`, `/inbox/ingest` |

Every action that changes something asks for confirmation first and, when it creates an approval item, shows its
ID: the agent prepares, a human decides. Every list has loading (skeleton), empty and error states.

Header: name, role badge, "Log out", "Log out everywhere". Sessions end after 30 minutes without activity; a
dialog warns 2 minutes before, and an expired session returns to the login page with a message.

## Security controls
- **Sessions**: random 256-bit token in an `HttpOnly; SameSite=Strict; Path=/api` cookie (`Secure` when `HG_COOKIE_SECURE=1`). Only its SHA-256 is stored, rotated at each login. Absolute TTL `HG_SESSION_TTL_MIN`, idle timeout `HG_SESSION_IDLE_MIN` (30 min).
- **CSRF**: double submit. The `csrf` value from login or `/auth/me` must be sent as `X-CSRF-Token` on every non-GET request (checked in `current_user`).
- **Passwords**: scrypt (n=2^14), 12+ characters with a common-password blocklist, invisible lockout (15 min after 5 failures, same answer as a wrong password), IP lockout with `Retry-After`. Details in [security_auth.md](security_auth.md).
- **Headers** (every response): CSP `default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'`, plus `nosniff`, `Referrer-Policy: no-referrer`, COOP/CORP same-origin, `X-Frame-Options: DENY`, `Cache-Control: no-store`. Swagger UI at `/api/docs` gets a relaxed policy (dev only).
- **Rate limits** (in-memory, per IP, per minute): login 10, CV upload 30, Answer Desk 30, everything else 300.
- **Body caps**: JSON 256 KB. Upload = `HG_MAX_UPLOAD_BYTES` + 64 KB, enforced on both the declared length and the streamed bytes. P1 still checks file type and page count.
- **Hostile text**: all candidate-derived text is rendered as React text nodes. There is no `dangerouslySetInnerHTML`/`innerHTML` in the frontend (grep is clean). Zero-width and bidi characters are made visible in the Security Center.
- **Hostile PDFs**: rendered with pdf.js to a canvas in a worker, `isEvalSupported: false`, XFA off, no iframe/object/plugin. The PDF endpoint should send `Content-Disposition: attachment`.

## Known limits
- The rate limiter is per process and in memory. That's fine for a single-node demo.
- `InboxItem` is typed from `email_gate._serialize` (`/inbox` returns lanes of `{intent, urgency, count, items[]}` groups). It is not frozen in `contracts.py`, so a change there must be mirrored in `types.ts`.
- Accessibility: skip link, visible focus rings, native `<dialog>` modals (focus trap, Esc), keyboard-selectable rows, `prefers-reduced-motion`. Colors keep WCAG AA contrast on the light and dark palettes.
