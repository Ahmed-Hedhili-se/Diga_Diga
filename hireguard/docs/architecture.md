# Platform architecture: one trust core, two modules

Owner: Ahmed (system design). Reviewers: Rayen (backend), Yasmina (frontend), Hedhili (model).

> **The AI reads, code decides, humans approve.**
> Whatever reads stranger text cannot act; whatever can act never reads stranger text.

The brief asks for an AI agent that takes over an HR team's daily work, with one golden rule: *the agent executes, the human decides about people*. We ship one product with two modules on a shared trust core:

- **HireGuard: Recruit** (HR and candidates).
- **HR Nexus: Team** (HR and staff).

## 1. System context

```
 Candidates ──PDF/email──►┌───────────────────────── TRUST CORE ─────────────────────────┐
 (untrusted)              │ Sanitizer → Detector → Extractor (local LLM, typed JSON only) │
                          │ → Validator (evidence offsets) → deterministic code           │
 Employees ──questions──► │ Approvals (risk, canaries, 2nd approver, attention guard)     │
                          │ → Executor (403 unless approved) → hash-chained audit, anchored│
                          │ Trust analytics: fairness audit · stability · attention        │
                          └──────────────┬───────────────────────────────┬────────────────┘
                                         │                               │
   ┌─────────────────────────────────────▼──────┐   ┌────────────────────▼─────────────────────┐
   │ RECRUIT (HireGuard)  roles R, M            │   │ TEAM (HR Nexus)  roles M, A (E: own docs) │
   │ Ranking + evidence, borderline badges      │◄──┤ Team skills map (holder counts only)      │
   │ Inbox digest, template replies             │ * │ HR process metrics (per stage)            │
   │ Interview slots, structured scorecards     │   │ Knowledge-gap radar (k ≥ 5)               │
   │ Fast-track: offer fit, follow-ups,         │   │ Answer Desk, self-service documents       │
   │   talent-pool rediscovery, offer letters   │   │ Roadmap: anonymous pulse survey (k ≥ 5)   │
   └────────────────────────────────────────────┘   └───────────────────────────────────────────┘
   * the only Team → Recruit flow: per-skill holder counts become a PROPOSED rubric that HR applies
```

**External services:**

- **Ollama** (Qwen3-8B), local only: candidate data never leaves the machine.
- **Mail:** a mock outbox in the demo. In production, SMTP behind the executor.
- **Audit anchoring:** a file, OpenTimestamps and git.

**Users:** recruiter (R), HR manager (M), employee (E), admin (A).

## 2. Modules

| Module | Feature | Code | Status |
|---|---|---|---|
| Trust core | Sanitizer, detector, extractor, validator | `backend/app/pipeline/` | built |
| | Approvals, canaries, executor, audit, anchor | `backend/app/workflow/` | built |
| | Fairness audit, shortlist stability, attention guard | `eval/fairness.py`, `scoring/stability.py`, `workflow/attention.py` | built |
| Recruit | Ranking with evidence, rubric, team-aware rubric proposal | `scoring/` | built |
| | Inbox digest, template replies, interview slots, scorecards | `workflow/` | built |
| | **Offer fit and pay-band coverage** | `scoring/offer_fit.py` | built |
| | **Offer letter** (salary inside the band, 2 approvers) | `scoring/offer_fit.py` | built |
| | **Candidate follow-ups** (at most 2) | `workflow/followups.py` | built |
| | **Talent-pool rediscovery** (opt-in, 2-year expiry) | `scoring/rediscover.py` | built |
| Team | **Team skills map** | `team/routes.py` and `scoring/team_gaps.py` | built |
| | **HR process metrics** (live audit log and labelled simulation) | `team/process_metrics.py`, `eval/process_sim.py` | built |
| | **Knowledge-gap radar** (logging hook) | `team/knowledge_gaps.py` | built; the Answer Desk must call `record()` |
| | Answer Desk | `pipeline/routes.py` | **returns 501, owner Rayen** |
| | Self-service documents | `workflow/documents.py` | built |

## 3. Data classes and boundaries

| Data class | Stored in | Who can read it | Retention | Leaves its module? |
|---|---|---|---|---|
| Candidate PII: CV, email, name | `candidates`, `pipeline_docs`, uploads | R, M | Life of the requisition. Talent pool: consent plus 2 years | No |
| Declared conditions (salary range, notice, work mode, commitments) | `candidate_conditions` | R, M | Same as the CV | No. Never used by the scorer (tested) |
| Talent-pool consent | `talent_pool` | R, M | 730 days, withdrawable (`DELETE /talent-pool/{id}`) | No |
| Hiring decisions: scores, shortlists, offers | `score_results`, `approval_items` | R, M (offers: M) | Audit retention | Stage timestamps only, aggregated per stage |
| Employee records and HR documents | `workflow/documents.py` tables | E (own), M | Employment plus legal retention | No |
| Team skills profiles (fictional; in production, consented and employee-editable) | `data/team/teams.json` | Code only | — | **Holder counts per skill only** |
| Answer Desk log | `answer_desk_log`: section, ISO week, language | M, A, via `radar()` only | 52 weeks | Aggregates with k ≥ 5 |
| Audit log | `audit_log` (append-only triggers and a hash chain) | M, A | Permanent | No |

**Allowed cross-module flows. There are two, both explicit and both aggregate:**

1. **Team → Recruit.** Per-skill holder counts (gap, single holder, covered) produce a *proposed* rubric. An HR manager applies it with an audited `PUT /jobs/{id}/rubric`. No member identity crosses the boundary.
2. **Recruit → Team.** Per-file stage timestamps from the audit log become per-stage count, median and p95. No candidate id or attribute appears in the output.

**Forbidden flows:**

- Candidate data must never be used to infer anything about employees.
- Employee or team data must never feed a hiring score (beyond flow 1).
- No individual score for any employee: no performance, productivity, stress, behaviour or "risk" score.

**Where k ≥ 5 is enforced:**

- **In code:** `team/knowledge_gaps.py::radar` (cells under 5 return `null` and are flagged suppressed).
- **Exception, documented:** the skills map shows exact holder counts, because finding single holders is the point. These are declared professional skills, never behaviour, and no names leave the store.
- **Roadmap:** the anonymous pulse survey must reuse the same suppression.

## 4. Where AI is used, and where it is not

| Step | AI? | Why |
|---|---|---|
| Read a CV into typed fields (skills with evidence offsets, dates, degree, languages) | **Yes**: local Qwen3-8B, JSON schema, no tools, no memory across documents | Multilingual reading (French, English, Arabic, Derja) is the hard part |
| Classify an email: language, intent and urgency enums | **Yes**: same model, enums only | Triage |
| Validate, score, rank, check stability, run the fairness audit | No, code | Explainable, testable, auditable (EU AI Act Art. 13) |
| Offer fit, follow-up selection, rediscovery, process metrics, radar | No, code | Every rule fits in a docstring |
| Write replies, invitations, follow-ups, offer letters | No: templates with typed slots from our DB | Nothing from stranger text reaches an outgoing message |
| Approve, send, book, release, commit | **Never AI**: human approval, then the executor | GDPR Art. 22; the brief's golden rule |

## 5. Workflows

**Recruit:**

1. Upload: PDF, plus optional declared conditions and talent-pool opt-in.
2. Sanitize, then detect (a signal for HR only).
3. Extract (LLM), then validate (code), then score (code). The result is a *proposed* score.
4. Ranking, with the borderline badge, offer-fit badge and fills-gap badge.
5. HR proposes a shortlist. It becomes an approval item, then the executor runs it, then it is audited.
6. Interview invitation: 3 slots. HR approves one, then the booking and email are sent.
7. Scorecard.
8. Offer letter: salary inside the band, 2 HR approvers who are not the author, then the executor.
9. Follow-ups: silent candidates get a template reminder, which goes through approval.

**Team:**

1. Approved source: declared skills, the audit log, or the Answer Desk's (section, week) log.
2. Minimization: no text and no identities are stored.
3. Aggregation: per team, per stage, or per section, with k ≥ 5 where it applies.
4. A caveated view: sample size and window are shown, and the simulation is labelled.
5. Human interpretation. Nothing in the Team module acts.

**Every state-changing action** is authorised server-side (roles, CSRF), approved, executed and recorded in the audit log. Failures are explicit (403, 404 or 422), never empty successes.

## 6. Permissions matrix (new surfaces)

| Endpoint | R | M | E | A |
|---|---|---|---|---|
| `GET /jobs/{id}/offer-fit`, `GET /jobs/{id}/rediscover`, `POST .../rediscover/invite` | ✓ | ✓ | | |
| `PUT /candidates/{id}/conditions`, `DELETE /talent-pool/{id}` | ✓ | ✓ | | |
| `POST /candidates/{id}/offer` | | ✓ | | |
| `GET /followups`, `POST /followups/draft` | ✓ | ✓ | | |
| `GET /team/skills`, `/team/process`, `/team/knowledge-gaps` | | ✓ | | ✓ |

## 7. What we refuse to build

| We do not build | Why |
|---|---|
| Stress, burnout or emotion inference | EU AI Act Art. 5(1)(f) prohibits emotion recognition at work. Our own E4 experiment: work signals predict stress weakly (AUC 0.64). Barrett et al. 2019 |
| Individual performance or productivity scores | EU AI Act Annex III 4(b) (high-risk); it breaks the golden rule; it can't be validated on fictional data |
| Personality or "culture fit" scores | Rivera 2012 (ASR): "fit" turns into cultural matching |
| A trained offer-acceptance predictor | Its best predictors are pay history (forbidden: Directive 2023/970), commute (a proxy for region) and family situation (a proxy for gender). Replaced by the offer-fit check on declared conditions |
| Scraping external profiles | Real personal data without consent; optimised targeting skews by gender and race (Ali et al. 2019). Replaced by the opt-in talent pool |
| Reading employees' email or chat | Monitoring; disproportionate under GDPR |

## 8. Risk register

| ID | Risk | Severity | Owner | Status, evidence |
|---|---|---|---|---|
| R1 | Model-mode robustness and extraction quality are unmeasured; only oracle (code-path) numbers exist | High | Hedhili | Open. `eval/harness.py --extraction llm`, `fairness.py --extraction llm`, `load_test.py --extraction llm` on the GPU laptop |
| R2 | The detector misses instruction payloads: English "Evaluator note" 4/4, Derja 3/3, Arabic 3/4 | Medium (the detector is a signal, not a control) | Hedhili | Open. `docs/evaluation.md` |
| R3 | The Answer Desk returns 501, so the Employee Questions feature can't be demoed and the radar has only seed data | High for the demo | Rayen | Open. Fallback: retrieval-only, cited passage word for word, "no match" goes to HR, call `knowledge_gaps.record()` |
| R4 | `GET /reviewer/stats` returns canary misses **per reviewer**: a per-person monitoring score, against section 7 | Medium | Rayen (Ahmed decides) | Open. Recommend removing it, or aggregating like `/approvals/attention` (by batch size, not by person). No UI uses it today |
| R5 | `main` commit `8f829d8` contains `node_modules` (3,273 files), `frontend/dist` and about 380 generated PDFs | Medium (repo hygiene, pre-merge gate) | Ahmed | Open. Revert on `main`; the generators rebuild the PDFs |
| R6 | Scorecard criterion `team_fit` invites "culture fit" judgements | Low | Rayen | Open. Rename to `collaboration` with job-related anchors |
| R7 | HR could read offer fit as a ranking signal | Medium | Yasmina, Rayen | Mitigated: not in the score (test `test_conditions_never_change_the_score`), UI copy, offers set inside the band |
| R8 | Talent-pool use without valid consent | Medium | Rayen | Mitigated: opt-in at upload, 730-day expiry, withdraw endpoint, audited, tested |
| R9 | Demo history (old outbox emails, answer-desk log, process simulation) mistaken for measurements | Low | Yasmina | Mitigated: `seed:history` marker, "Simulation" banner, and this note |

## 9. References

**Security:**

- OWASP Top 10 for LLM Applications 2025 (LLM01 prompt injection).
- Greshake et al. 2023, "Not what you've signed up for", indirect prompt injection (arXiv 2302.12173).
- S. Willison 2023, "The Dual LLM pattern".
- Debenedetti et al. 2025, "Defeating Prompt Injections by Design" (CaMeL, arXiv 2503.18813).
- Zhang et al., USENIX Security 2026, "Measuring Real-World Prompt Injection Attacks in LLM-based Resume Screening" (arXiv 2605.28999): about 1% of about 197k real CVs carried hidden injections.
- Boston Globe, 7 Oct 2025: Greenhouse found white text in about 1% of 300M CVs.
- Schneier & Kelsey 1999, "Secure audit logs to support computer forensics".

**Fairness and law:**

- EEOC Uniform Guidelines, 29 CFR 1607.4(D) (four-fifths rule).
- NYC Local Law 144 (bias audits of automated employment decision tools).
- Dastin, Reuters 2018 (Amazon's recruiting tool).
- Mobley v. Workday (N.D. Cal.; ADEA collective certified May 2025).
- Ali et al. 2019, "Discrimination through optimization" (CSCW).
- EU AI Act, Regulation (EU) 2024/1689: Art. 5(1)(f), 10, 12, 13, 14(4)(b), 15(5); Annex III 4(a)/(b).
- GDPR Art. 22.
- EU Pay Transparency Directive 2023/970, Art. 5 (pay range before the interview; no pay-history questions; transposition 7 Jun 2026).
- Tunisia: Organic Law 2004-63 and the INPDP.
- CNIL recruitment guidance (keep applicant data at most 2 years after the last contact).

**Human oversight and selection:**

- Parasuraman & Manzey 2010, "Complacency and bias in human use of automation" (Human Factors).
- Goddard et al. 2012, automation bias review (JAMIA).
- Sackett, Zhang, Berry & Lievens 2022, revisited validity of selection procedures (J. Applied Psychology): structured interviews rank highest.
- Rivera 2012, "Hiring as cultural matching" (ASR).

**Process and employee questions:**

- Little 1961, L = λW (Operations Research).
- SHRM benchmarking: median time-to-fill 39 days in 2026, 44 in 2025 (non-executive).
- CareerBuilder 2016 (357 HR managers): pay below expectations accounts for 37% of declined offers, and another offer for 37%.
- Cronofy 2019: 3 or more emails to schedule one interview.
- Sweeney 2002, k-anonymity.
- Moffatt v. Air Canada, 2024 BCCRT 149 (a company is liable for its chatbot's answers).
- Lewis et al. 2020, retrieval-augmented generation.

**Skills:**

- ESCO (European Commission) skills taxonomy.
- Avelino et al. 2016, truck factor (ICPC).

**What we refuse to build:**

- Barrett et al. 2019, "Emotional expressions reconsidered" (PSPI).
- Kristensen et al. 2005, COPSOQ (Scand. J. Work Environ. Health).
