# Person 3 (P3): workflow & security backend, report for the team

> The AI reads, code decides, humans approve.
> P3 owns the code with authority: email gate, drafting, approvals, executor, audit log, documents, interviews, follow-ups.
> This file is kept up to date after every P3 task. **Section 1 is what I need from you.**

Last update: 2026-10-31 · branch `p3/docs` (includes T1-T6) · backend tests: 187 passed + 1 expected failure (P4 finding F5)

---

## 1. What I need from you

| # | For | Request | Why | Status |
|---|---|---|---|---|
| H1 | **P1** | Add a severity to each hidden finding: `severity: "high" \| "low"` on `HiddenFinding` (or a separate `undecodable` channel). Mark a lone U+FFFD glyph (common in Arabic words inside FR/EN CVs) as `low`. Real zero-width or tag characters stay `high`. Tell me which option you pick. **P3 side is done**: when you create an approval item, pass `hidden_findings` as the list of finding dicts (`channel`, `text`, `severity`), or pass `hidden_findings_high` as an int. A plain int in `hidden_findings` still works but counts as all high | My risk score now counts only high-severity findings, so clean Arabic-name CVs aren't pushed into the high-risk lane. Until you add `severity`, I already treat a zero_width finding whose text starts with `[N undecodable glyphs]` as low, so please keep that text format or tell me if it changes | open (P3 part done)
| H2 | **P1** | `pipeline/answer_desk.py` doesn't exist yet, but the threat model cites it. When you build `/api/answer-desk/ask`, send personal questions (leave, salary, certificate, contract) to my queue with `create_employee_question(user, topic, text)` (coming in my T3). Don't answer them yourself | Personal questions must go to HR, never to generated text | **ready**: T3 is merged-ready, see section 2 |
| H3 | **P1** | `docs/pipeline.md` doesn't exist. I replaced the broken link in `hireguard/README.md` with plain text "(P1, still to be written)". Please write the file and put the link back. Also: the threat model now says `/api/answer-desk/ask` returns 501 until you add handbook retrieval | Deliverable completeness | open |
| H4 | **P2, P4** | When you change a **candidate's** hiring status, create a `status_change` approval item with `object_type: "candidate"`, `object_id: <candidate_id>`, `status_to: "rejected" \| "hired" \| "withdrawn" \| ...` | Follow-up reminders skip closed candidates by reading this. Any other `object_type` won't be seen | please confirm |
| H5 | **P4** | Follow-ups UI: a "Silent candidates" card on `GET /api/followups/preview` and a "Draft reminders" button on `POST /api/followups/run` (roles R, M). The reminders then appear in the normal approval queue, with `payload.template = "followup_reminder"` | New spec-book axis "Candidate Follow-ups" | **done (P4)**: Approvals page, "Silent candidates" card |
| H7 | **P4** | Approval queue: an interview-slot item can turn `rejected` after another slot is booked (audit action `approval.withdraw`, `details.reason = "sibling_booked"`). Show it as "withdrawn: another slot was booked" instead of a plain rejection | Reviewers shouldn't think a colleague rejected it | **P4**: the queue returns only pending items, so withdrawn slots just disappear; the interview batch explains it. See `hireguard/P4_NOTES.md` N7 |
| H8 | **P4** | Security Center: show `GET /api/audit/verify` (ok / broken_at / last_anchor) and an admin "Anchor now" button (`POST /api/audit/anchor`). Step-by-step in `hireguard/docs/demo_p3.md` | Demo moment 4 | **done (P4)**: Security Center → Audit log |
| H9 | **P4** | Fix **F5**: a locked account answers `423` but an unknown one answers `401`, so anyone can learn which emails have accounts. Return the same status and message for both. Then remove the `xfail` mark on `test_login_does_not_reveal_whether_an_account_exists` in `tests/test_pentest_p3.py` | Pentest finding F5 (low) | **done (P4)**: lockout is invisible, `xfail` removed |
| H10 | **P4** | Before deploying: disable `/api/docs` (it has a relaxed CSP) and decide how the rate limiter sees client IPs behind a proxy (today it uses the socket peer, so everyone behind one proxy shares 10 logins a minute). Details in `hireguard/docs/pentest_report.md`, O1 and O2 | Pentest observations | **O1 done** (`HG_API_DOCS=0`), O2 open (P4_NOTES N5) |
| H11 | **P1** | Demo step 2 needs the email extractor. Without Ollama running, every email gets `extraction_failed` and stays in `needs_human` with no draft (safe, but the demo shows nothing). Either have Ollama up on demo day, or add an offline fallback in `pipeline/email_extract.py`, like the CV `ground_truth` mode | Demo robustness | open |
| H6 | **everyone** | Run `pip install -r hireguard/backend/requirements.txt` before testing. PyMuPDF was missing on my laptop, so 3 test files couldn't load | So tests don't fail at import | info |

Reply by editing the **Status** column (or tell me directly).

---

## 2. What you can use from P3 today

### HTTP (full list in `hireguard/contracts/API.md`)
- Inbox: `GET /api/inbox` (lanes routine / needs_human / suspicious), `POST /api/inbox/{id}/release-request`
- Approvals: `GET /api/approvals`, `POST /api/approvals/{id}/decision`, `POST /api/approvals/batches/{batch_id}/decision`
- Executor: `POST /api/executor/run/{item_id}`. **403 if the item is not approved** (the demo moment)
- Audit: `GET /api/audit`, `GET /api/audit/verify`, `POST /api/audit/anchor`
- Employee questions (new): `POST /api/employee-questions` (E), `GET /api/employee-questions[/{id}]` (E own, M all), `POST /api/employee-questions/{id}/reply` (M, template enum)
- Documents: `POST /api/documents/request`, `GET /api/documents/mine`, `GET /api/documents/{id}/download`
- Interviews: `POST /api/interviews/{id}/scorecard`, `GET /api/interviews/reminders`, `GET /api/calendar/slots`
- **New:** `GET /api/followups/preview`, `POST /api/followups/run`

### Python (in-process)
```python
from app.workflow.approvals import create_item   # every action goes through an approval item
from app.workflow.audit import append            # pass conn=conn to log inside your transaction
from app.workflow.executor import register_handler  # override how an approved kind is executed
from app.workflow.employee_questions import create_employee_question  # P1: create_employee_question(user, topic, text) -> {id, topic, risk, status}; topic in leave|salary|certificate|contract|other
```

### Rules your code must respect
- Never send, book, release or change status directly. Create an approval item; the executor does the rest.
- Never put text from a CV or an email body into an outbound message. Templates and DB slots only.
- Recipients come from the verified address in `candidates`, never from `From` / `Reply-To`.

---

## 3. P3 progress

| Task | What | Status |
|---|---|---|
| T1 | Candidate follow-up reminders (drafted, never auto-sent; max 2 per candidate) | **done** (`1cab8ea`) |
| T2 | Booking one interview slot withdraws the 2 sibling slots; no double booking | **done** |
| T3 | `employee_question` queue for personal Answer Desk questions | **done** (unblocks H2) |
| T4 | Risk score ignores low-severity hidden findings | **done** on my side (H1 still wanted from P1) |
| T5 | Audit anchoring docs + offline/online check | **done** |
| T6 | Internal pentest (IDOR, CSRF, executor, email spoofs, template injection, rate limits) → `docs/pentest_report.md` | **done**: 3 P3 findings fixed, 1 finding + 2 observations handed to P4, 1 to P1 |
| T7 | Docs consistency + threat model update | **done** |

## 4. Changelog

- **2026-10-31 · T1**: `workflow/followups.py`, templates `followup_reminder.{fr,en,ar}.txt`, 2 endpoints, 7 tests. A candidate is "silent" when our last email to their verified address is older than N days (default 3) and no verified inbound email came after it. Spoofed mail counts neither as a reply nor as a language signal.
- **2026-10-31 · T2**: executing an `interview_booking` withdraws the other slot proposals of the same inbox message + candidate + job (status `rejected`, audit `approval.withdraw` / `sibling_booked`), in the executor's transaction. A withdrawn item then gets 403 on execute and 409 on approve. The calendar already refused a booked slot (409, whole action rolls back). 5 tests in `tests/test_booking.py`.
- **2026-10-31 · T3**: `workflow/employee_questions.py` + 4 endpoints + `question_reply.{fr,en,ar}.txt`. Personal Answer Desk questions go to HR: typed `topic` enum, risk computed from topic only, text stored for HR to read and never logged, never copied to a reply. HR picks a reply template (`received`, `contact_hr`, `use_documents`); it becomes an `email_send` approval item to the employee's own account (from `auth_users`), needs a second HR manager, and marks the question `answered` when the executor sends it. Another employee's ticket id gives 404. 7 tests in `tests/test_employee_questions.py`. **P1: for `/api/answer-desk/ask`, return `{kind: "routed", ticket_id: <id>}` using the id from `create_employee_question`.**
- **2026-10-31 · T4**: `approvals.compute_risk` adds +10 only for high-severity hidden findings (`count_high_findings`). Low = `severity: "low"`, or a `zero_width` finding that is only undecodable glyphs. Missing field or unknown shape = high (fail closed). Explicit `hidden_findings_high` int wins. 13 tests in `tests/test_risk.py`.
- **2026-10-31 · T5**: `anchor_now` now reads the head and does the `ots`/`git` work **before** its write transaction (a slow push no longer blocks approvals) and only runs git when `data/anchors` is its own repo (before, `git commit` could have acted on the HireGuard repo). 12 tests in `tests/test_anchor.py` (offline = no external call, network flag, tamper / delete / full-rewrite / truncation all caught). New docs: `docs/anchoring.md` (what we claim, Windows setup), `docs/demo_p3.md` (5-step demo script), Postgres `REVOKE`/`GRANT` in the threat model. `python -m app.workflow.demo --followups` adds a backdated email so the follow-up demo works. `data/anchors/` is git-ignored.
- **2026-10-31 · T6**: `tests/test_pentest_p3.py` (59 cases) + a live run of the server with `curl` (demo steps 3, 4, 5 and the 429 check verified). Fixed in P3 code: **F1** duplicate `Authentication-Results` with our authserv-id (email gate), **F2** unlimited calendar rows (`/api/calendar/slots` now 404s for unknown recruiters), **F3** control and bidi characters in template slots. Also fixed the demo helper `python -m app.workflow.demo --followups` (it found nobody to remind because the seeded emails are timestamped "now"; it now backdates that candidate's mail, and logs it). Full write-up: `hireguard/docs/pentest_report.md`.
- **2026-10-31 · T7**: README no longer links the missing `docs/pipeline.md`; the threat model now points at `pipeline/routes.py` (there is no `pipeline/answer_desk.py`) and says the Answer Desk is 501 until P1 lands retrieval. Threat model gained the T1-T6 controls, the new email rows (IDN homograph, encoded-word display name, duplicate auth-results), the pentest table, and the three residual risks we state openly (visible keyword stuffing, fake dated jobs in visible text, compromise of the laptop). `hireguard/docs/p3_handoffs.md` is a pointer to this file.

## 5. P3 status summary

All seven tasks of the hardening pass are done: T1 follow-ups, T2 no double booking, T3 employee questions, T4 risk score, T5 audit anchoring, T6 pentest, T7 docs. Backend tests: 187 passed + 1 expected failure (P4's finding F5).
Docs: `hireguard/docs/anchoring.md`, `pentest_report.md`, `demo_p3.md` (5-step demo), `p3_handoffs.md`, `threat_model.md`.
Open for others: H1 (P1), H2 (P1), H3 (P1), H4 (P2/P4), H5 (P4), H7 (P4), H8 (P4), H9 (P4), H10 (P4), H11 (P1).
Work is on local branches `p3/followups` → `p3/booking` → `p3/employee-questions` → `p3/risk` → `p3/audit-anchor` → `p3/pentest` → `p3/docs` (each builds on the previous; `p3/docs` has everything). Nothing is pushed yet.
