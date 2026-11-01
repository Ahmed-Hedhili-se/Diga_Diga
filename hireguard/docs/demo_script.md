# Demo script (about 4 minutes)

All people, CVs and emails are fictional. Numbers are never quoted from memory: read them from **Security Center >
Evaluation**, which shows the mode (model or oracle) of every number.

## Before the demo

```powershell
cd hireguard
.\run.ps1 -Seed          # prints the demo passwords once; with Ollama up the CVs go through qwen3:8b
```

Check: the Candidates list shows **no "offline extraction" badge** if you want to say "the model read these CVs".
If the badge is there, use the backup path below and say so.

## Click path

| # | Who | Do | Say |
|---|---|---|---|
| 1 | Recruiter | Candidates > JOB-DATA-01. Click a score justification | "Code ranks from validated fields only. Each line points to the evidence in the CV. The score is *proposed*." |
| 2 | Recruiter | Open CAND-006 | "Hidden white and tiny text was removed before the model read the CV, and flagged for HR. Flags never change a score." |
| 3 | Recruiter | Open CAND-002, then CAND-008 (same CV, other town) | "Same qualifications, same score: towns, schools and gendered titles are masked before the model reads the CV." |
| 4 | HR manager | Security Center > Blocked attacks, then Evaluation | Read the attack, twin and email numbers **with their k/n and mode**. Name one limit (for example the CV-language twins). |
| 5 | Employee | My documents > request a work certificate | "The document exists only after an HR manager releases it." |
| 6 | Recruiter | Approvals > "Execute without approval" | "403: the executor refuses anything not approved, and the refusal is in the audit log." |
| 7 | HR manager | Approve the certificate, then Money | "Hours saved come from real counted actions; minutes per task are estimates until the HR interviews." |

## Backup path (GPU or model unavailable)

1. Seed offline: stop Ollama, run `.\run.ps1 -Seed` (the CVs fall back to ground-truth extraction) and set
   `HG_EXTRACT_MODE=ground_truth` so emails get their labelled fields.
2. The UI then shows **"offline extraction"** on every candidate. Say it: *"This run uses labelled demo data, not
   the model. The model's measured results are on the Evaluation tab."*
3. Steps 2, 5, 6 and 7 work the same: the sanitizer, validator, approvals, executor and audit log need no model.
4. If the laptop fails, play the backup video, recorded with the model running.

## Do not say

- "The AI decided" or "the AI hired": code proposes, a person approves.
- "Attacks never work": quote the measured k/n.
- "0/40" from an oracle run: oracle numbers test the code path, not the model.
