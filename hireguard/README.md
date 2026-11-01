# HireGuard

Secure AI HR system: SUP'COM hackathon. One platform, two modules on one trust core:

- **Recruit (HireGuard):** HR and candidates. Screening with evidence, inbox triage, replies, interviews, and a fast-track to the offer.
- **Team (HR Nexus):** HR and staff. Team skills map, HR process metrics, Answer Desk knowledge gaps, self-service documents. Aggregates only, never individual scores.

Architecture, data boundaries, permissions, risk register and references: [docs/architecture.md](docs/architecture.md). Team assignments: [../persons/README.md](../persons/README.md).

Business side: the case and its evidence level are in [docs/business.md](docs/business.md) (every external figure in [docs/evidence.md](docs/evidence.md); `python scripts/check_claims.py` fails on an unsourced percentage). Customer discovery kit: [docs/discovery](docs/discovery/call_script.md) (call script, French outreach message, pilot letter template, call log; `python scripts/discovery_summary.py` prints what the pitch may quote).

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

## Access control

Every API route needs a permission from one matrix ([backend/app/auth/permissions.py](backend/app/auth/permissions.py)),
and a test walks the route table to prove it. **Separation of duties:** the Admin manages accounts and the platform
but cannot open a CV, a score, the inbox or an employee question, and cannot approve or execute anything. The
Security Center, which the Admin shares with HR, shows only the attack fragments stripped from CVs. Details: [docs/security_auth.md](docs/security_auth.md).

## Sections

- Architecture and data boundaries: [docs/architecture.md](docs/architecture.md) (Ahmed)
- Design system (colour tokens, components, light and dark themes): [docs/design_system.md](docs/design_system.md) (Rayen)
- Document pipeline: [docs/pipeline.md](docs/pipeline.md) (P1)
- Threat model (OWASP LLM Top 10 2025 + web): [docs/threat_model.md](docs/threat_model.md) (P3)
- Evaluation: [docs/evaluation.md](docs/evaluation.md) (P2)
- Frontend and web security: [docs/frontend.md](docs/frontend.md) (P4)
- Authentication and access control (permission matrix, lockout, sessions): [docs/security_auth.md](docs/security_auth.md) (P4)
- Odoo ERP connector (optional, off by default): [docs/erp_odoo.md](docs/erp_odoo.md)

## Trust analytics

Code that checks the system *and* the humans around it. Nothing here makes a decision.

- **Group fairness audit** (`eval/fairness.py`, Security Center → Fairness audit): selection-rate ratios by region, school, gender and CV language, with permutation tests, a proxy test on the scored fields, and a planted-bias positive control.
- **Shortlist stability** (`GET /jobs/{id}/stability`): a candidate whose top-k place flips when rubric weights move ±15%, or who is exactly tied at the cut-off, gets a *borderline* badge and should be reviewed one by one.
- **Team-aware rubric** (`GET /jobs/{id}/team-gaps`): skills the role's team lacks or holds in one person become a *proposed* rubric. An HR manager applies it through the normal, audited rubric edit.
- **Attention guard** (`GET /approvals/attention`): canary misses by batch size. After missed canaries, routine batches shrink and bulk approval is capped (EU AI Act Art. 14(4)(b), automation bias).

## Fast-track (Recruit)

Hiring is slow at the end, not the start: salary mismatches found after the interviews, candidates who go quiet, offers waiting for paperwork. Each feature is code, and every outgoing message is an approval item.

- **Offer fit** (`GET /jobs/{id}/offer-fit`): each candidate's own declared conditions (salary range, notice period, work mode, commitments) checked against the job's published terms, plus a job-level *band coverage* ("the band covers 1 of 2 declared expectations in your top 2"). Shown beside the ranking, never inside it. This replaces an "acceptance probability" model, whose best predictors (pay history, commute, family situation) are proxies we refuse to use.
- **Offer letter** (`POST /candidates/{id}/offer`, HR manager): salary set by HR inside the published band (EU Pay Transparency Directive 2023/970), drafted from a template, approved by 2 HR managers who are not the author.
- **Follow-ups** (`GET /followups/preview`, Approvals → Silent candidates): a candidate who has not answered our last sent email for 3+ days gets a template reminder in the approval queue; at most 2, never to rejected, hired or withdrawn candidates.
- **Talent-pool rediscovery** (`GET /jobs/{id}/rediscover`): past applicants who opted in, re-scored with the new job's rubric; consent expires after 2 years and can be withdrawn.

## HR Nexus (Team)

Team insights page (HR manager, admin). Measures processes, declared skills and handbook coverage, never people.

- **Skills map** (`GET /team/skills`): holder counts per needed skill (gap, single holder, covered). Gaps feed the team-aware rubric proposal.
- **HR process** (`GET /team/process`): median and p95 days per hiring step from the audit log, bottleneck step, Little's law. A fresh demo has no history, so `eval/process_sim.py` provides a **labelled** simulation.
- **Knowledge gaps** (`GET /team/knowledge-gaps`): which handbook sections employees ask about, and the share with no match; only (section, week, language) is logged; cells under 5 are hidden.

## Known limits

- Candidate portal (magic link) is on the roadmap; the demo uses pre-verified candidate addresses.
- The interview loop closer is built but not demoed.
- The knowledge-gap radar mixes a fictional seed log with the live Answer Desk questions (section and week only); say so in the demo.
- Model numbers come from the 1 Nov run **with identity masking** on Modal (Qwen3-8B, NVIDIA L4): attacks 3/40 vs 13/40 for a standard screener; twin CVs 17/89 (26/90 before masking), of which CV-language swaps 13/20; skill F1 0.944 on 200 CVs (Arabic 0.80); load test 100 CVs, 0 errors, p50 9.9 s. Visible attacks (7/14) are a stated limit. Code-path (oracle) results are labelled as such everywhere.
- The demo uses SQLite with triggers for the audit log; production uses a Postgres role restricted to INSERT/SELECT.
