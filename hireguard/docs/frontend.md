# Frontend, auth and web security (P4)

## Run
- Dev: `uvicorn app.main:app --port 8000` in `backend/`, then `npm run dev` in `frontend/` → http://localhost:5173 (Vite proxies `/api`).
- Prod/demo: `npm run build`; FastAPI serves `frontend/dist` from the same origin under the strict CSP → http://localhost:8000.
- Demo users: `python -m app.seed` in `backend/` prints 5 random passwords **once**. There are no default accounts.

## Pages and roles
| Page | Roles | API |
|---|---|---|
| Candidates (ranking, score breakdown, click → evidence in text/PDF, propose shortlist) | Recruiter, HR Manager | `/jobs`, `/candidates`, `/candidates/{id}/text`, `/candidates/{id}/pdf`, `/jobs/{id}/shortlist` |
| Approvals (routine batches + diff, high-risk one by one, 2nd approver for offers, "execute without approval" → 403) | Recruiter, HR Manager | `/approvals`, `/approvals/{id}/decision`, `/approvals/batches/{id}/decision`, `/executor/run/{id}` |
| Inbox digest (routine / needs human / suspicious) | Recruiter, HR Manager | `/inbox` |
| Security Center (hidden text per channel, injection flags, audit chain) | HR Manager, Admin | `/security/findings`, `/audit`, `/audit/verify` |
| Money dashboard | HR Manager, Admin | `/money`, `/money/settings` |
| Answer Desk | Employee, HR Manager | `/answer-desk/ask` |
| My documents | Employee | `/documents/request`, `/documents/mine`, `/documents/{id}/download` |
| Interview scorecard | Recruiter, HR Manager | `/interviews/{id}/scorecard` |
| Users | Admin | `/auth/users` |

Role-based navigation is a convenience only. Every endpoint enforces its role server-side, and object-level checks belong to each endpoint's owner.

## Security controls
- **Sessions**: random 256-bit token in an `HttpOnly; SameSite=Strict; Path=/api` cookie (`Secure` when `HG_COOKIE_SECURE=1`). Only its SHA-256 is stored. TTL `HG_SESSION_TTL_MIN`.
- **CSRF**: double submit. The `csrf` value from login or `/auth/me` must be sent as `X-CSRF-Token` on every non-GET request (checked in `current_user`).
- **Passwords**: scrypt (n=2^14), at least 12 characters for new users, lockout for 15 min after 5 failures, and identical errors for an unknown user and a wrong password.
- **Headers** (every response): CSP `default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'`, plus `nosniff`, `Referrer-Policy: no-referrer`, COOP/CORP same-origin, `X-Frame-Options: DENY`, `Cache-Control: no-store`. Swagger UI at `/api/docs` gets a relaxed policy (dev only).
- **Rate limits** (in-memory, per IP, per minute): login 10, CV upload 30, Answer Desk 30, everything else 300.
- **Body caps**: JSON 256 KB. Upload = `HG_MAX_UPLOAD_BYTES` + 64 KB, enforced on both the declared length and the streamed bytes. P1 still checks file type and page count.
- **Hostile text**: all candidate-derived text is rendered as React text nodes. There is no `dangerouslySetInnerHTML`/`innerHTML` in the frontend (grep is clean). Zero-width and bidi characters are made visible in the Security Center.
- **Hostile PDFs**: rendered with pdf.js to a canvas in a worker, `isEvalSupported: false`, XFA off, no iframe/object/plugin. The PDF endpoint should send `Content-Disposition: attachment`.

## Known limits
- The rate limiter is per process and in memory. That's fine for a single-node demo.
- The `InboxItem` shape is not frozen in `contracts.py`, so the Inbox page renders optional fields defensively (`from`, `subject`, `received_at`, `intent`, `urgency`, `auth.{spf,dkim,dmarc}`, `reasons[]`, `candidate_id`).
