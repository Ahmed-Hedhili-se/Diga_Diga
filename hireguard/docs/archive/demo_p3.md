# P3 demo script (5 steps, about 2 minutes)

Setup once: `.\run.ps1 -Seed` and note the printed passwords. Log in as `recruiter@hireguard.demo`, `hrm@hireguard.demo` and `hrm2@hireguard.demo` in three browser profiles (or sessions).

| # | Say | Do | Expect |
|---|---|---|---|
| 1 | "A stranger pretends to be candidate A." | Inbox → open **EML-011** (spoofed, DMARC fail) | Lane **suspicious**, status `held`, no candidate linked, no draft, no data shown |
| 2 | "A real candidate asks for an interview." | Inbox → **EML-003** (routine) → Approval queue shows **3 slot proposals** with a template reply → approve one and run it | Interview created, invite in the outbox, the **other two proposals become `rejected`** (audit `approval.withdraw`, reason `sibling_booked`) |
| 3 | "Even a logged-in user cannot send without approval." | Terminal, below | **HTTP 403**, and `executor.refused` appears in the audit log |
| 4 | "And nobody can quietly rewrite history." | Security Center → audit **verify** → `ok: true`. Admin: **Anchor now** → receipt (`anchor-<seq>.json`, status `pending` offline or `anchored`) | `ok: true`, `last_anchor` filled in |
| 5 | "Nobody is forgotten." | Candidates → **Draft reminders** (`POST /api/followups/run`) | Reminder drafts for silent candidates wait in the approval queue, nothing sent |

## Step 3 commands

```powershell
# log in (cookie jar + CSRF token), then try to run an item nobody approved
curl -c jar -H "Content-Type: application/json" -d '{"email":"recruiter@hireguard.demo","password":"<printed by seed>"}' http://localhost:8000/api/auth/login
# the response contains "csrf"; pick any pending item id from GET /api/approvals
curl -i -b jar -H "X-CSRF-Token: <csrf>" -X POST http://localhost:8000/api/executor/run/<pending-item-id>
# HTTP/1.1 403 Forbidden  {"detail":"item is not approved: nothing was executed"}
```

## If something goes wrong

- Step 5 shows nothing: a reminder needs an email sent more than N days ago with no reply, and the seed has no such history. Run once, from `hireguard\backend`: `python -m app.workflow.demo --followups` (adds one clearly-labelled backdated acknowledgement for the first candidate who never wrote to us), then click **Draft reminders**.
- Step 2 shows no drafts: the candidate must exist (`.\run.ps1 -Seed` seeds candidates before the inbox).
