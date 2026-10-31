# Authentication and access control (P4)

HireGuard handles CVs, salaries and personal HR questions. Access follows two rules:
people see only what their job needs, and the person who runs the platform does not read HR data.

Code: [backend/app/auth/](../backend/app/auth/). Tests: [test_rbac.py](../backend/tests/test_rbac.py),
[test_auth.py](../backend/tests/test_auth.py).

## Permission matrix

One file, [`permissions.py`](../backend/app/auth/permissions.py), defines the permissions, which role holds which,
and which permission each API route needs. `/api/auth/me` sends the caller's permissions to the frontend, which
builds its menu, pages and buttons from them. The backend still checks every request: hiding a button is
a convenience, not a control.

| Permission | Recruiter | HR Manager | Employee | Admin |
|---|:-:|:-:|:-:|:-:|
| `candidates.read`, `candidates.upload` | ✅ | ✅ | | |
| `scores.read`, `scores.rescore`, `shortlist.propose` | ✅ | ✅ | | |
| `rubric.edit` | | ✅ | | |
| `approvals.decide` (routine), `approvals.execute` | ✅ | ✅ | | |
| `approvals.decide_high_risk` (offers, documents, leave, held mail, 2nd approver) | | ✅ | | |
| `inbox.read`, `followups.manage`, `calendar.read`, `interviews.scorecard` | ✅ | ✅ | | |
| `inbox.release_request`, `interviews.reminders`, `questions.reply`, `documents.release` | | ✅ | | |
| `documents.request` (own), `questions.ask` | | | ✅ | |
| `documents.read`, `questions.read` (own for employees, all for HR) | | ✅ | ✅ | |
| `answer_desk.ask` | | ✅ | ✅ | |
| `security_center.read`, `audit.read`, `money.read` | | ✅ | | ✅ |
| `money.edit` | | ✅ | | |
| `users.manage`, `audit.anchor`, `inbox.ingest`, `erp.configure` | | | | ✅ |
| `erp.status` | ✅ | ✅ | | ✅ |
| `erp.import` | ✅ | ✅ | | |

**Separation of duties.** The admin manages accounts, anchors the audit log and loads demo mail, but cannot open
a CV, a score, the inbox or an employee question, and cannot approve or execute anything. The admin keeps the
Security Center, which shows the hidden fragments stripped from CVs and the candidate's name, not the CV itself;
drop `security_center.read` from the admin row if your policy wants even that out of IT's reach. An IT admin who wants
to read CVs has to give themselves an HR role. They can't do that on their own account (409), and creating a
second account leaves a trace in the audit log.

**Object level.** When a URL contains an ID, the owning module checks that the object belongs to the caller and
answers **404, not 403**, so IDs can't be probed: an employee asking for another employee's document or
question gets the same answer as for an ID that doesn't exist (`test_employee_cannot_read_another_employees_document_or_question`).

**Proof.** `test_rbac.py` reads FastAPI's route table and checks:
- every route appears in `ROUTE_PERMISSIONS`, and every entry still matches a route;
- the guard on each route allows exactly the roles the matrix gives;
- every role without the permission gets a real `403` from the running app;
- every allowed role gets past the guard on read routes;
- every state-changing route rejects a forged CSRF token, even for allowed roles;
- anonymous calls get `401` everywhere except login and health.

So a teammate who adds an unprotected route, or protects it differently from the matrix, breaks the build.

## Authentication flow

```
Browser                         API                                   SQLite
  │ POST /auth/login {email,pw}   │                                     │
  │──────────────────────────────►│ IP locked?  ── yes ──► 429 + Retry-After
  │                               │ read user + account lock (no write lock held)
  │                               │ scrypt(pw) against the user's hash, or a dummy hash
  │                               │ (same cost for unknown / inactive / locked accounts)
  │                               │ write tx: count failure or clear it, audit ────────►│
  │◄──────── 401 "Invalid email or password" (any failure, including a lock)
  │◄──────── 200 Session + Set-Cookie hg_session (new random token; old cookie destroyed)
  │                               │                                     │
  │ GET/POST … cookie + X-CSRF    │ session: hash(token) → user, active?│
  │──────────────────────────────►│ absolute expiry? idle > 30 min? ──► 401 "session expired"
  │                               │ CSRF header == session csrf? ─────► 403
  │                               │ role holds the permission? ───────► 403 (audited)
  │                               │ object belongs to caller? ────────► 404
```

| Control | Setting |
|---|---|
| Password hashing | scrypt, n=2^14, r=8, p=1, 16-byte salt |
| Password policy | 12 to 256 characters, blocklist of common passwords, must not contain the email name. No composition rules (NIST SP 800-63B) |
| Account lockout | 5 failures in 15 min → locked 15 min. Invisible: the answer is the same as a wrong password (fixes pentest F5) |
| IP lockout | `HG_LOGIN_IP_MAX_FAILED` (20) failures in 15 min → `429` with `Retry-After`. Higher than the account limit because call centers share one NAT address |
| Rate limit | 10 logins per minute per IP (in memory) |
| Session token | 256-bit random, only its SHA-256 stored, rotated at every login |
| Session lifetime | absolute `HG_SESSION_TTL_MIN` (8 h), idle `HG_SESSION_IDLE_MIN` (30 min). The UI warns 2 minutes before |
| Session revocation | logout, `POST /auth/logout-all`, deactivation, role change, password reset |
| Cookie | `HttpOnly; SameSite=Strict; Path=/api`, `Secure` when `HG_COOKIE_SECURE=1` |
| CSRF | double submit: `X-CSRF-Token` must equal the session's token on every non-GET request |
| Default accounts | none: the seed prints random passwords once |
| Audit | `auth.login`, `auth.login_failed` (with reason), `auth.lockout`, `auth.login_blocked`, `auth.logout`, `auth.logout_all`, `auth.user_create`, `auth.user_update`, `auth.password_reset`, `auth.permission_denied`. Never a password, hash or token |

## Threats and mitigations

| Threat | Mitigation | Test |
|---|---|---|
| Brute force / password spraying | Account lock after 5 failures, IP lock after 20, 10 logins/min/IP, scrypt cost | `test_lockout_after_5_failures_is_invisible_and_expires`, `test_ip_lockout_answers_429_with_retry_after`, `test_login_rate_limited` |
| Account enumeration | Same status, message and hashing cost for unknown, inactive, locked and wrong-password logins | `test_wrong_password_and_unknown_user_look_same`, `test_unknown_emails_lock_the_same_way`, `test_login_does_not_reveal_whether_an_account_exists` |
| Session theft / fixation | HttpOnly cookie, hashed token at rest, rotation at login, idle and absolute expiry, logout-all | `test_login_rotates_the_session_token`, `test_idle_timeout`, `test_logout_all_kills_every_session_of_the_user` |
| CSRF | SameSite=Strict plus double-submit header on every write | `test_state_changing_routes_need_csrf_even_for_allowed_roles` |
| XSS from candidate or employee text | React text nodes only, no `dangerouslySetInnerHTML` / `innerHTML` (grep clean), strict CSP without `unsafe-inline` | `test_security_headers_present`, pentest `test_stored_hostile_text_is_served_as_json_never_as_html` |
| IDOR | Owner check in the owning module, 404 for "not yours" | `test_employee_cannot_read_another_employees_document_or_question` |
| Privilege escalation | Permission guard on every route, proven by the matrix test; role changes are admin-only, audited, and close sessions | `test_every_denied_role_gets_403_and_every_allowed_role_gets_through`, `test_deactivation_and_role_change_kill_sessions` |
| Insider admin | Separation of duties: no HR data, no approvals; can't change own role | `test_admin_cannot_read_candidates_or_decide_hr_items`, `test_admin_cannot_demote_or_deactivate_themselves` |
| Weak passwords | Length and blocklist on create and reset; resets generate a random temporary password | `test_password_policy`, `test_reset_password_and_unlock` |

## Residual risks

- No second factor yet. TOTP for HR managers and admins is the next step (see `P4_NOTES.md`).
- Lockout and rate-limit counters are per process. Several API workers would need a shared store.
- Behind a reverse proxy, set `HG_TRUSTED_PROXIES` to the proxy's address: `X-Forwarded-For` is then read right to left, skipping trusted hops. Without it the header is ignored and everyone behind the proxy shares one rate-limit bucket (pentest O2, `test_client_ip_trusts_forwarded_for_only_from_listed_proxies`).
- A malicious admin can create an HR account. It is audited but not prevented: in production, require a second admin to approve role grants.
