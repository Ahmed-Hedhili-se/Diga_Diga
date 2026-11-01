# Security hardening: what is enforced, what is open

Written for a company's security reviewer. Every row says how it was checked. Nothing here is a claim about a
system that has been attacked in production: it is a code review, an internal pentest ([pentest_report.md](pentest_report.md))
and automated tests. Threat model: [threat_model.md](threat_model.md). Risk register: [architecture.md](architecture.md) section 8.

## Design principle (what makes injection bounded)

The model reads untrusted text and returns **typed JSON with no free-text field**; code validates every field
against the visible text; deterministic code scores; a human approves every consequential action; the executor
refuses anything not approved. A fully manipulated model output can only choose values inside the schema, and each
of those values has to survive the validator and a human. Measured: 3/40 hidden-channel attacks moved a result
(naive screener 13/40), 7/14 visible attacks moved one (naive screener 8/14): see [evaluation.md](evaluation.md).
The model is **not** a security boundary; the validator, the scorer and the approval gate are.

## Enforced and tested (1 Nov 2026)

| Control | What it does | Where | Test |
|---|---|---|---|
| Production mode fails closed | `HG_ENV=production` refuses to start unless: secure cookies, API docs off, https-only CORS origins, no cloud model provider without `HG_ALLOW_CLOUD_LLM=1`, remote model hosts on https, Odoo on https, PDF isolation on | `app/hardening.py`, called at startup in `main.py` | `tests/test_production_mode.py` |
| HSTS | `Strict-Transport-Security` (one year, subdomains) whenever `HG_COOKIE_SECURE=1` | `app/security.py` | `test_production_mode.py` |
| PDF parsing isolation | Uploaded PDFs are opened only in a separate worker process: a 20 s deadline kills a stuck parse, a crashing worker breaks only its own request, 1 GiB address-space cap on POSIX | `app/pipeline/isolation.py`, `service.py` | `tests/test_isolation.py` (deadline, crash, recovery, identical verdicts) |
| Password hashing | scrypt N=2^16, r=8, p=2 (OWASP equivalent minimum); parameters stored in each hash; old hashes still verify and are upgraded at the next good login; a tampered cost in the database cannot hang a login | `app/auth/core.py`, `auth/routes.py` | `tests/test_auth.py` |
| Delimiter spoofing | Our `<document>` / `<email>` data tags are broken inside untrusted text whatever the case or spacing (was exact-match only) | `app/pipeline/delimiters.py` | `tests/test_delimiters.py` |
| Dependency vulnerabilities | Backend pins moved to versions with no known advisory: `starlette` 0.41.3 (14 advisories) to 1.10.0, `python-multipart` 0.0.20 (12, the upload parser) to 0.0.33, `dnspython`, `pytest`; frontend `react-router-dom` 6.28.0 to 6.30.6 (3 high advisories, including XSS via open redirects) | `backend/requirements.txt`, `frontend/package.json` | `pip-audit`: no known vulnerabilities; full backend suite (536 tests) passes on the pinned stack |
| Model output cap | Every model call is capped at 2,048 generated tokens (`HG_LLM_MAX_TOKENS`). Found on 1 Nov: one request kept generating (39,000+ tokens, still running after 20 minutes) and held the GPU, which also explains the 258 s worst case in the load test and the failed extraction calls. A hostile CV could do this on purpose. The longest of 417 valid outputs is about 650 tokens | `app/pipeline/llm.py`, `config.py` | `tests/test_llm_remote.py` |
| Model transport | Modal answers requests longer than about 150 s with a 303 "resume" redirect. The client now follows it, **only to the same origin**; a redirect to another host is refused and receives no credentials | `app/pipeline/llm.py` | `tests/test_llm_remote.py` |
| Sessions, CSRF, lockout, headers, CSP, body caps, audit chain, approvals | As reviewed in the code (see below) | `auth/`, `security.py`, `workflow/` | `test_auth.py`, `test_rbac.py`, `test_release_gate.py`, `test_pentest_p3.py` |

Strong from the start (read in the code): session tokens stored only as hashes, `HttpOnly` + `SameSite=Strict` cookie,
idle and absolute expiry, double-submit CSRF on every state change, one uniform login failure (no user enumeration),
account and IP lockouts, no default accounts, a strict CSP with no inline scripts, body caps that also cover chunked
uploads, downloads served as attachments, every 403 audited, an append-only hash-chained audit log, no self-approval,
distinct approvers for offers, planted canaries, and status-gated execution so a replay cannot run twice.

## Open: not enforced yet

| # | Gap | Why it matters | What closes it | Owner |
|---|---|---|---|---|
| S1 | No multi-factor authentication for HR managers and admins | One phished password reaches candidate PII and can approve offers | TOTP (RFC 6238) for `hr_manager` and `admin`, enforced at login; recovery codes | Rayen (backend), Yasmina (enrolment screen) |
| S2 | No self-service password change; an admin-issued temporary password stays valid and the admin knows it | Shared knowledge of a credential; no way to rotate on suspicion | Change-password endpoint; force a change at first login after a reset | Rayen |
| S3 | Data at rest is plaintext (SQLite file and uploaded PDFs); retention is documented but not enforced (R11) | A stolen disk or backup exposes every candidate | Disk encryption as a deployment requirement; Postgres with an insert-only audit role; purge job and delete-on-request endpoint | Ahmed (policy), Rayen |
| S4 | Model and runtime are not pinned: `modal_ollama.py` installs Ollama with `curl \| sh` and pulls `qwen3:8b` by tag | An upstream change alters behaviour, and the evidence measured here, silently | Pin the Ollama version and the model digest; refuse to serve on a mismatch (the digest is recorded in `docs/model_config.md`) | Hedhili |
| S5 | Email classifier injection is untested: the 10 injection emails aim at the "verified" flag (code decides that), none aims at the intent or urgency labels the model sets | A manipulated label can move a sensitive request (withdrawal, document, leave) into the routine lane; a human still approves the reply | An email-injection test set; send sensitive intents to a human regardless of the label when the text looks like an instruction | Hedhili |
| S6 | Adaptive attacks and the outsider set are not run | The model has open weights and the prompt is public: an attacker can optimise a payload offline against a replica | Red-team against a local replica; open the 30 sealed outsider attacks once | Hedhili, Ahmed |
| S7 | One model call per CV, no cross-check | A single manipulated extraction goes straight to the validator | Two extractions with different prompt order or model; disagreement goes to a human | Hedhili |
| S8 | The audit chain is not keyed: anyone who can write the database file can rewrite it consistently | Tamper evidence depends on the external anchors (OpenTimestamps), not on the chain alone | Keep anchors on in production and verify them; Postgres with an insert-only role | Rayen |
| S9 | Rate limiter is in memory and per process; a 5-failure lockout lets an attacker lock a named account for 15 minutes | Lost on restart; not shared across workers; targeted lockout | Shared store (Redis or the database); progressive delay instead of a hard lock | Rayen |
| S10 | Every recruiter can read every candidate | Insider risk; data minimisation | Scope candidates to requisitions | Rayen, Ahmed |
| S11 | Email sending is simulated (outbox table); no real SMTP | The real outbound surface (header injection, deliverability) is untested | Test it when SMTP is added | Rayen |
| S12 | No malware scanning of uploads; no SAST, SBOM or CI vulnerability gate | Supply chain and file-borne risk | Run `pip-audit` and `npm audit` in CI; add an upload scanner if required by a customer | Ahmed |

## Before a pilot with real candidate data

1. Run with `HG_ENV=production` behind HTTPS (the server will not start otherwise) and keep `HG_PARSE_ISOLATION=1`.
2. Keep the model on-premises in Tunisia (Law 2004-63); never enable `HG_LLM_PROVIDER=gemini` or the Groq fallback with real data.
3. Encrypt the disk; schedule backups with the same protection.
4. Close S1 (MFA) and S2 (password change). Close S4 (pin the model).
5. Re-run the evaluation on the production configuration and attach the result files.

## How to re-check

```powershell
cd hireguard\backend
python -m pip_audit -r requirements.txt          # no known vulnerabilities
python -m pytest -q                              # 536 tests
cd ..\frontend
npm audit --omit=dev                             # 2 moderate remain (see below)
```

`npm audit` still reports 2 moderate advisories in `react-router`; its suggested fix is a major version change
(`--force`) that has not been tested here.
