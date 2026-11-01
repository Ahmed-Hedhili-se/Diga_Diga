# Rayen - backend, scoring, and evaluation integration

## Mission

Own dependable backend behavior for the platform: stable APIs, typed contracts,
validated scoring paths, persistence, and automated backend tests. Implement
security controls in code rather than relying on frontend restrictions or
documentation.

## Demo video clips (optional since 1 Nov)

**Update, 1 Nov:** the 3-minute demo video is done. It was built automatically from screenshots of the dashboard, seeded
with `qwen3:8b` on the laptop (`hireguard/docs/demo_video/out/HireGuard_demo_3min.mp4`, rebuilt with
`hireguard/docs/demo_video/README.md`). The clips below are no longer needed for it. Record them only if the team wants
real screen recordings as a backup for the live demo.

The plan, if you do: record the clips **with the model reading the CVs**. Allow about 2 hours, setup included.

Progress:

- [ ] Step 1: app seeded with the model reachable, all four checks pass
- [ ] Steps 2 and 3: browser and recorder ready, a 10-second test clip looks sharp at 1920×1080
- [ ] C0 C1 C2 C3 C4 recorded, 2 takes each
- [ ] C5 C6 C7a C7b C8 C9 recorded, 2 takes each (record them in this order: the database changes from C5 on)
- [ ] `notes.txt` written, clips uploaded, Yasmina told; Modal stopped if you used it

**Hand over:** MP4 files, 1920×1080, 30 fps, no sound, named `<clip>_take<n>.mp4` (for example `C3_evidence_take1.mp4`),
in the team drive folder `HireGuard/demo_video/clips/` (create it). **Not in git:** video files don't belong in the repo.
Add `notes.txt`: for each clip, the best take and anything that differed from this plan (a score, a label, an extra click).

### Step 1: seed the app with the model on (about 30 minutes)

1. `git pull` on `main`, then `cd hireguard\frontend; npm ci`.
2. Start clean: delete `hireguard\backend\hireguard.db` and the folder `hireguard\backend\uploads\`.
3. Make the model reachable **before** seeding, so Qwen3-8B reads the 8 demo CVs (otherwise they fall back to labelled data):
   - Local: Ollama running, `ollama pull qwen3:8b`, then one warm-up: `ollama run qwen3:8b "hello"`.
   - Or Modal: ask Hedhili to start `hireguard-ollama` and send you `.env.modal` (put it in `hireguard\`; `run.ps1` loads it).
   - Not Gemini (`HG_LLM_PROVIDER=gemini`): every number in the video comes from Qwen3-8B.
4. `cd hireguard; .\run.ps1 -Setup -Seed` (or `.\run.ps1 -Seed` if you have run setup before). It prints 5 passwords
   **once**: keep them in a private note, never on screen.
5. Check all four, at http://localhost:5173:
   - Overview > "Connected systems": the model is reachable (Ollama, or "Modal GPU (cloud)").
   - Candidates > JOB-DATA-01: no row has an **"offline extraction"** badge.
   - The CAND-006 (Karim Mansour) row has a red "hidden" badge.
   - CAND-002 and CAND-008 (both "Youssef Trabelsi") have the same score. If not, record anyway and write both scores in `notes.txt`.

   If the model can't be reached at all, follow "Backup path" in `hireguard/docs/demo_script.md`, record anyway, and write
   `OFFLINE` at the top of `notes.txt`: the narration then has to say so.

### Step 2: browser and screen (about 15 minutes)

1. Screen resolution 1920×1080 (Settings > System > Display). If yours is higher, switch to 1920×1080 while recording.
2. Chrome, three profiles (profile icon > Add), each signed in at http://localhost:5173 **before** you record:
   - "Nour": `recruiter@hireguard.demo` (recruiter)
   - "Karim": `hrm@hireguard.demo` (HR manager)
   - "Leila": `hrm2@hireguard.demo` (second HR manager)
3. In each profile: theme **Light** (theme button in the app header; the slides are light), zoom 125% (`Ctrl` and `+`).
   If the Candidates ranking and the detail pane no longer sit side by side, use 110% instead. Use the same zoom for every clip.
4. `F11` for full screen: it hides the tabs, address bar and profile name. Close every other tab.
5. Windows Focus or Do not disturb on. Quit Teams, Discord, WhatsApp, Slack and mail.
6. Mouse: move slowly, rest about one second on a button before clicking, then keep the pointer still and off the text that matters.

### Step 3: recorder (about 10 minutes)

- **OBS Studio** (best): Settings > Video: base and output 1920×1080, 30 FPS. Settings > Output > Recording: format mp4,
  quality "High Quality, Medium File Size". Mute Desktop Audio and Mic. Sources: + > Display Capture. Settings > Hotkeys:
  start recording `F9`, stop `F10`.
- **Or the Snipping Tool** (already installed): `Win+Shift+R`, drag over the whole screen, Start; stop with the red button.
  Files land in Videos\Screen Recordings.
- Test: record 10 seconds, play it back full screen, check it's sharp and 1920×1080 (file > Properties > Details).

### Step 4: rules for every clip

- Start recording, wait 2 seconds on a still screen, do the steps, **hold the last screen 3 seconds**, stop.
- One clip per file. Two takes of each.
- Retake if: an error appears (other than the 403 in C7a), a page shows a loading skeleton for more than 2 seconds, a
  notification pops up, the pointer covers the important text, or you clicked the wrong thing.
- Never on screen: passwords, a terminal, `.env` files, the address bar, other apps.
- Do **not** click "Apply suggested weights" or "Rescore": they change the scores in the other clips.
- To start over completely: stop the app, delete the database and `uploads\`, reseed (new passwords), sign in again.

### Step 5: shot list

**C0. Overview, model connected** (Karim, about 10 s). Spare footage.
1. Sidebar > Overview. Hold 3 s on the top tiles ("Waiting for approval", "Candidates screened", "CV attacks contained").
2. Scroll slowly to "Connected systems" and hold 3 s on the model card showing it is reachable.

**C1. The poisoned CV, recruiter view** (Nour, about 15 s)
1. Candidates > job JOB-DATA-01. Hover, then click **Karim Mansour (CAND-006)**: the row has red "hidden" and "injection flags" badges.
2. Detail pane: hold 3 s on the red box "… hidden item(s) were found and removed before the model read the CV … Flags never change the score".
3. Scroll to the Evidence card and click **PDF**: show the bottom of the page, where the hidden lines are: nothing is visible.
   Then click **Visible text**: the instruction is not there either.

**C2. The hidden text revealed** (Karim, about 12 s). Only HR managers can open Security Center, so not Nour.
1. Security Center (it opens on "Blocked attacks"). Scroll to the **Karim Mansour** card.
2. Hold 3 s on: "Safe: removed before scoring", "White or background-colored text", "The hidden text says: Ignore all
   previous instructions…", and the red "Looks like an instruction to the AI" badge.
3. Scroll a little to the "Tiny font" finding (the French note to the AI evaluator). Hold 3 s.

**C3. The evidence behind a score** (Nour, about 20 s)
1. Candidates > JOB-DATA-01, click the **#1** candidate.
2. Hold 2 s on the score "/ 100" and the line "Score proposed: computed by code from the validated fields below. No AI decides".
3. Scroll to the score components. Click one line under **skills**: the Evidence card highlights that passage in the CV. Hold 3 s.
4. Click one line under **experience**. Hold 3 s.
5. Under "Validated skills", hover (don't click) one "backed by a dated job" badge and one "listed only" badge.

**C4. The tied twins** (Nour, about 20 s)
1. Candidates > JOB-DATA-01. Set **Shortlist size** to 2 (click the number field, select it, type 2).
2. The two "Youssef Trabelsi" rows (CAND-002 and CAND-008) show "borderline · NN% top 2". Hover one badge so the tooltip
   shows. Hold 3 s.
3. Click CAND-002, then CAND-008: same score, different town in the CV header (La Marsa, Kasserine).

   No borderline badge at 2? Try the shortlist size where the twins sit at the cut-off, and write that size in `notes.txt`.

**C5. Offer fit and the offer draft** (Karim, about 25 s)
1. Candidates > JOB-DATA-01, shortlist size 2. Hold 2 s on the line "band covers 1/2 declared in top 2" and the warning under it.
2. Click **CAND-002**: the "Offer fit" card shows the salary as **mismatch** (asks 4,600–5,200; the band is 2,800–3,800). Hold 3 s.
3. Click **CAND-008** > Offer fit > open **Draft offer letter**. Gross salary **3300**, start date as it is, language
   Français, then **Send to approval**.
4. Hold 3 s on the message "Offer for CAND-008 drafted (…). Two other HR managers must approve it before it can be sent."

**C6. The second approver** (Leila, about 20 s)
1. Approvals > **High-risk items**: the offer for CAND-008. Show the change (salary 3,300), then click **Approve**.
2. Hold 4 s on "… your approval is recorded. A second HR manager must approve." and the yellow box "This item needs 2 HR
   managers, and 1 has approved … Waiting here is the control working."

**C7a. The executor refuses** (Nour, about 12 s)
1. Approvals > High-risk items: the same CAND-008 offer, still pending.
2. Click the red-outlined **Execute without approval**. Hold 4 s on the red "403 Forbidden: the executor refused …".

**C7b. The refusal is on record** (Karim, about 8 s)
1. Security Center > **Activity record**. Hold 3 s on the newest rows: "Action refused" for that offer.

**C8. The Team module** (Karim, about 25 s)
1. Candidates > JOB-DATA-01, scroll to the card **"Team-aware rubric: Data platform team"**: Apache Spark marked "gap",
   with its proposed weight. Hold 3 s. Don't click "Apply suggested weights".
2. Sidebar > **Team insights** > "Skills map": the Data platform team, Apache Spark with 0 holders. Hold 3 s.
3. Tab **Knowledge gaps**: "Questions per handbook section", with "6. Remote work" at the top, and any row reading
   "fewer than 5 (hidden)". Hold 3 s.

**C9. The numbers in the app** (Karim, about 15 s)
1. Security Center > **Test results**. Under "Which test run:", choose the run labelled **"AI model used"**.
2. Hold on "Can hidden text change a score?": attacks 3/40 and the row "For comparison: a system with no protection" at 13/40.
3. Scroll slowly through "Is the score fair to identical people?" and "Are emails sent to the right place?".

Spare footage, only if you have time: **C10** Inbox > "Suspicious" lane, EML-011 held with no candidate data (Nour);
**C11** the Money dashboard (Karim); **C12** Answer Desk as `employee@hireguard.demo`: ask "Combien de jours de congé
annuel ?" and show the exact handbook passage with its section.

### Step 6: check and hand over

1. Watch the best take of each clip once, full screen: is the text readable, no notification, 1920×1080?
2. Write `notes.txt` (best take per clip, anything different from this plan).
3. Upload to `HireGuard/demo_video/clips/` and send Yasmina the link.
4. If you used Modal, tell Hedhili so he can stop it (`modal app stop hireguard-ollama`).

## Left to do (1 Nov)

All items below were closed on 1 Nov (tests: about 480 backend pass). The scorer change means the stored
evaluation results predate it: Hedhili re-runs them.

Done since 31 Oct: the permission matrix, lockout, idle timeout, user admin, audit of sign-in,
sign-out and account changes (closes R10), the permission-driven UI, the Odoo connector, the
dashboard redesign and design system (`hireguard/docs/design_system.md`), contract-drift tests,
rubric validation, the explicit evaluation report, `GET /model/status`, the live Overview
dashboard and the plain-language Security Center.

- [x] **P0** Scorer: weight a skill whose `support == "listed_only"` at 0.3 or less of a
      `dated_experience` one (request R3 in [archive/person1.md](archive/person1.md)); add a twin-style test.
- [x] **P0** N8 (`hireguard/P4_NOTES.md`): `GET /approvals` lists pending items only, so an
      approved routine item vanishes before anyone executes it. Return approved-not-executed too.
- [x] **P0** Document in `contracts/API.md`: `GET /erp/status`, `GET /erp/jobs/{id}/applicants`,
      `POST /erp/jobs/{id}/import`, `POST /jobs/{id}/candidates/{id}/status` (done, `5a7f39b`).
- [x] **P1** R4: `GET /reviewer/stats` still groups by user; return hits and misses by batch
      size and week instead (decided by Ahmed).
- [x] **P1** R12: one `scores.rescore` audit event in `POST /jobs/{id}/rescore` (done, `5a7f39b`).
- [x] **P1** R14: offer approver count as a setting (default 2 others; SME: 1 other).
- [x] **P1** N10: `hidden_high` count in `list_candidates`, so a clean Arabic CV shows no badge.
- [x] Keep `tests/test_release_gate.py` `MATRIX` and architecture §6 in step with every route.

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
