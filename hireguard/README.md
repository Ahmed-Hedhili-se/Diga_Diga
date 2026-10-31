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

- Document pipeline: [docs/pipeline.md](docs/pipeline.md) (P1), demo script [docs/demo_p1.md](docs/demo_p1.md)
- Threat model (OWASP LLM Top 10 2025 + web): [docs/threat_model.md](docs/threat_model.md) (P3)
- Evaluation: [docs/evaluation.md](docs/evaluation.md) (P2)
- Frontend and web security: [docs/frontend.md](docs/frontend.md) (P4)

## Known limits

- Candidate portal (magic link) is on the roadmap; the demo uses pre-verified candidate addresses.
- The interview loop closer is built but not demoed.
- The demo uses SQLite with triggers for the audit log; production uses a Postgres role restricted to INSERT/SELECT.
