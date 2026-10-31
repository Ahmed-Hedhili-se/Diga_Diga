# HireGuard

Secure AI HR system: SUP'COM hackathon.

> **The AI reads, code decides, humans approve.**
> Whatever reads stranger text cannot act; whatever can act never reads stranger text.

## Run

```powershell
copy .env.example .env
.\run.ps1 -Setup -Seed     # first time: venv, npm install, demo data (prints generated passwords once)
.\run.ps1                  # API on :8000 (docs at /api/docs), UI on :5173
ollama pull qwen3:8b       # local extractor model
```

## Architecture

```
PDF / email ──► Sanitizer ──► Detector (signal only) ──► Extractor (Qwen3-8B, JSON schema, no tools)
   (untrusted)    P1            P1                         P1
                                                             │ typed fields only
                                                             ▼
                              Validator (offsets ∈ visible text, ESCO labels, dates) ──► Scorer (rubric, code)
                                 P1                                                      P2  → "proposed"
                                                             │
                                                             ▼
             Approval service (risk queue, batches, canaries, 2nd approver) ──► Executor (403 if unapproved)
                P3                                                               P3
                                                             │
                                                             ▼
                                         Append-only hash-chained audit log, anchored  (P3)
```

Contracts: [contracts/API.md](contracts/API.md) and [backend/app/contracts.py](backend/app/contracts.py).

## Sections

- Document pipeline: [docs/pipeline.md](docs/pipeline.md) (P1)
- Threat model (OWASP LLM Top 10 2025 + web): [docs/threat_model.md](docs/threat_model.md) (P3)
- Evaluation: [docs/evaluation.md](docs/evaluation.md) (P2)
- Frontend and web security: [docs/frontend.md](docs/frontend.md) (P4)

## Trust analytics

Code that checks the system *and* the humans around it. Nothing here makes a decision.

- **Group fairness audit** (`eval/fairness.py`, Security Center → Fairness audit): selection-rate ratios by region, school, gender and CV language, with permutation tests, a proxy test on the scored fields, and a planted-bias positive control.
- **Shortlist stability** (`GET /jobs/{id}/stability`): a candidate whose top-k place flips when rubric weights move ±15%, or who is exactly tied at the cut-off, gets a *borderline* badge and should be reviewed one by one.
- **Team-aware rubric** (`GET /jobs/{id}/team-gaps`): skills the role's team lacks or holds in one person become a *proposed* rubric. An HR manager applies it through the normal, audited rubric edit.
- **Attention guard** (`GET /approvals/attention`): canary misses by batch size. After missed canaries, routine batches shrink and bulk approval is capped (EU AI Act Art. 14(4)(b), automation bias).

## Known limits

- Candidate portal (magic link) is on the roadmap; the demo uses pre-verified candidate addresses.
- The interview loop closer is built but not demoed.
- The demo uses SQLite with triggers for the audit log; production uses a Postgres role restricted to INSERT/SELECT.
