# Demo script (2 minutes inside the 5-minute pitch)

Owner: Yasmina. The only demo script: it merges Yasmina's script with the pitch runbook (1 Nov); the older
per-person scripts are in `archive/`. The spoken lines and timing are in [`pitch.md`](pitch.md).

All people, CVs and emails are fictional. Numbers are never quoted from memory: read them from **Security Center >
Evaluation**, which shows which run (model or code path) produced every number.

## Before the demo (one hour before)

```powershell
cd hireguard
.\run.ps1 -Setup -Seed   # first time; later .\run.ps1 -Seed. About 2 minutes. Prints the demo passwords ONCE.
```

1. Store the passwords. Open three logged-in browser profiles:
   - recruiter Nour (`recruiter@hireguard.demo`)
   - HR manager Karim (`hrm@hireguard.demo`)
   - second HR manager Leila (`hrm2@hireguard.demo`)
2. With Ollama up, the seeded CVs go through qwen3:8b; send one warm-up request first.
3. Check the Candidates list: if it shows an **"offline extraction"** badge, the model did not read these CVs. Use the
   backup path below and say so.
4. **Never upload a CV live through the model:** it takes about 40 seconds per CV on the hardware we measured.
5. Zoom 125%, notifications off, the backup video open in a tab.

## Click path (about 2 minutes)

| # | Who | Do | Say (short) | Must be visible |
|---|---|---|---|---|
| 1 | Recruiter | Candidates > JOB-DATA-01, click a score justification | "Code ranks from validated fields only; each line points to the evidence. The score is *proposed*." | The highlighted evidence in the CV |
| 2 | Recruiter | Open CAND-006 | "Hidden white and tiny text was removed before the model read the CV, and flagged for HR. Flags never change a score." | The findings, with the hidden text revealed |
| 3 | Recruiter | Shortlist size 2: CAND-002 and CAND-008 (same CV, other town) | "Tied. Any ranker picks one by sort order; we flag it as borderline and leave it to a human." If the two scores differ, say so: twin results are being re-measured after masking. | "borderline · 51% / 49% top 2" |
| 4 | HR manager (Karim), then Leila | Offer-fit card, CAND-002's badge, then CAND-008 > "Draft offer letter", 3,300 TND > Send to approval. Leila: Approvals > approve | "We found the deal-breaker before the interview. We don't predict who accepts: we ask, and we check against the published band." | "band covers 1/2"; CAND-002 "offer mismatch"; the offer **pending, 1 of 2 approvals**: the control working. To clear it on stage, Karim sets the rule to 1 on the Approvals page ("Offer approval rule", audited), which is what a one-HR-manager SME would do |
| 5 | Recruiter | Approvals > any pending item > "Execute without approval" | "403: the executor refuses anything not approved, and the refusal is in the audit log." | Red "403 Forbidden" |
| 6 | HR manager | Team insights > Skills map, then Knowledge gaps | "We measure the process and the handbook, never the people." Say "fictional demo log". | Apache Spark "gap"; Remote work on top; cells under 5 hidden |

If time allows, one line each: employee certificate released only after an HR manager approves (My documents);
hours saved counted from real actions (Money); silent candidates get one templated reminder (Approvals).

## Backup path (GPU or model unavailable)

1. Seed offline: stop Ollama, run `.\run.ps1 -Seed` (the CVs fall back to ground-truth extraction) and set
   `HG_EXTRACT_MODE=ground_truth` so emails get their labelled fields.
2. The UI then shows **"offline extraction"** on every candidate. Say it: *"This run uses labelled demo data, not
   the model. The model's measured results are on the Evaluation tab."*
3. Steps 1, 2, 4, 5 and 6 work the same: the sanitizer, validator, approvals, executor and audit log need no model.
4. If the laptop fails, play the backup video, recorded with the model running, from the same step.

**Between rehearsals:** delete `backend/hireguard.db` and `backend/uploads/`, then reseed.

## Do not say

- "The AI decided" or "the AI hired": code proposes, a person approves.
- "Attacks never work": quote the measured k/n (3/40 vs 13/40 for a standard screener).
- "0/40" or "0/89" without "code path": those runs use no model.
- "Data never leaves the machine": the model runs locally **by default**; for the hackathon it also ran on a
  rented cloud GPU, with fictional data only.
