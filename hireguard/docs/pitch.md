# HireGuard: 5-minute pitch (final draft, 31 Oct)

> Rules for every number on stage:
> - It comes from `eval/results/*.json` or the HR interview notes, as k/n with its 95% interval.
> - A row still marked **TBD** one hour before the pitch is cut, not guessed.
> - Oracle (code-path) results are never presented as model results.

## Script (5:00)

| Time | Slide | Say | On screen |
|---|---|---|---|
| 0:00–0:25 | Hook | "An HR assistant in Sfax gets 300 CVs for one Data Engineer job. Researchers scanned 197,000 real CVs this year: about one in a hundred hides text meant only for the AI (USENIX Security 2026). So three CVs in her pile are talking to the machine, not to her." *Once the baseline is measured, add:* "We tried them on a standard AI screener: k of 40 worked." | Title, then one CV with its white text revealed |
| 0:25–0:50 | Problem | "HR teams spend the day sorting, replying and chasing; a hire takes 39 days at the median in SHRM's benchmark. AI agents can do this work, but they read strangers' text *and* they can act. That combination is the vulnerability." | Problem slide: [TBD from the interviews] minutes per CV, 39-day median |
| 0:50–1:15 | Principle | "HireGuard: the AI reads, code decides, humans approve. One trust core, two modules: Recruit for candidates, Team for staff." | Two-module diagram (`docs/architecture.md` §1) |
| 1:15–1:45 | Demo 1 | "Here is the poisoned CV." Security Center shows the hidden text revealed. Candidates: the score did not move. Click a score: every point is highlighted in the CV. | Demo, beat 1 |
| 1:45–2:05 | Demo 2 | "These two are tied. Any ranker picks one by sort order. We flag it as borderline and leave it to a human." | Demo, beat 2 |
| 2:05–2:30 | Demo 3 | "Before the interviews: CAND-002 wants 4,600; the published band stops at 3,800. We don't predict who will accept: we ask, and we check. The offer letter is drafted inside the band and waits for two HR managers." | Demo, beat 3 |
| 2:30–2:50 | Demo 4 | "Nothing leaves without a human." Run an unapproved item: **403**. "And if reviewers start rubber-stamping, the batches shrink." | Demo, beat 4 |
| 2:50–3:15 | Demo 5 | "HR Nexus: the data team has nobody with Spark, so the hiring rubric proposes it. Employees ask most about remote work. We measure the process and the handbook, never the people." | Demo, beat 5 |
| 3:15–3:55 | Proof | Read 3 rows of the metrics slide: attacks, planted bias caught, load test. Say what is not measured yet. | Metrics slide |
| 3:55–4:35 | Business | Beachhead, pricing, pilots asked, then one line on compliance: "built to the EU AI Act, which ESNs serving EU clients will need". | Business slide, compliance table |
| 4:35–5:00 | Close | "What we refuse to build: emotion AI, performance scores, culture fit. HireGuard does the paperwork; people decide about people." Then the ask. | Refuse-to-build slide, then the ask |

Money dashboard, documents and follow-ups are cut from the live demo. Mention them in one line if time allows.

## Demo runbook

**One hour before:**

1. Run a fresh seed: `cd hireguard; .\run.ps1 -Setup -Seed`. It takes about 2 minutes and prints the passwords **once**, so store them.
2. Start Ollama and send one warm-up request. If the model is down, the seed falls back to fixture extractions and **prints a warning**: say "offline mode" on stage, never "live model".
3. Open three logged-in browser profiles:
   - recruiter Amira (`recruiter@hireguard.demo`)
   - HR manager Karim (`hrm@hireguard.demo`)
   - second HR manager Leila (`hrm2@hireguard.demo`)
4. Set zoom to 125%, turn notifications off, open the backup video in a tab.

**Click path (Karim unless noted):**

| Beat | Clicks | What must be visible |
|---|---|---|
| 1 | Security Center → CAND-006, then Candidates → CAND-006 → a score component | White-text and tiny-font findings with the text revealed; "did not change the score"; the evidence highlight |
| 2 | Candidates, JOB-DATA-01, shortlist size 2 | CAND-002 and CAND-008 both "borderline · 51% / 49% top 2" |
| 3 | Same page: offer-fit card → CAND-002 badge → CAND-008 → "Draft offer letter", 3,300 TND → Send to approval. Then switch to Leila → Approvals → approve it | "band covers 1/2 declared in top 2"; CAND-002 "offer mismatch"; the offer stays **pending, 1 of 2 approvals** (a third manager would sign: say so) |
| 4 | Approvals → any pending routine item → "Execute without approval" | Red "403 Forbidden: the executor refused…" |
| 5 | Team insights → Skills map → Knowledge gaps | Data team: Apache Spark "gap"; Remote work leads; under-5 cells hidden. Say "fictional demo log" |

**If something breaks:**
- Switch to the backup video at the same beat; don't debug on stage.
- If the Answer Desk is still not built (risk R3), hide its menu entry; don't show an error page.

**Between rehearsals:** delete `backend/hireguard.db` and the `backend/uploads/` folder, then reseed.

## Metrics slide

Measured 31 Oct in oracle mode: real sanitizer, detector, validator and scorer, with ground-truth extraction. Rows marked LLM need Hedhili's run on the GPU laptop.

| Claim | HireGuard | Baseline (same model) |
|---|---|---|
| In-house attacks that moved a field, score or rank: through the model (LLM) | TBD k/40 | TBD k/40 (`eval/baselines.py` is still a stub, R1) |
| In-house attacks that moved a field, score or rank: code path | 0/40 (95% CI 0.0–8.8%) | — |
| Hidden-text detection | 40/40 attacks found (95% CI 91.2–100%), 0 false alarms on 40 clean twins | — |
| Score changed by town, school, gap, language or gender form (code path) | 0/89 (95% CI 0.0–4.1%) | — |
| Fairness audit catches a planted biased criterion | yes: adverse-impact ratio 0.28, p = 0.005; 100% of the gap traced to the degree component | — |
| 300 CVs through pipeline and database (code path) | 0 errors, p95 45 ms per CV | — |
| Extraction F1 on 200 CVs (LLM) | TBD | — |
| 300 CVs through the model (LLM) | TBD | — |

Cut before stage unless measured: outsider attacks (sealed set), ResumeShield, ranking against outside annotators.

Footnote on the slide: "Clopper-Pearson 95% intervals; n shown for every rate. Zero successes out of 40 bounds the true rate below 8.8%; claiming under 5% needs 72 or more attacks with zero successes."

Two claims to say out loud:

- "With the same 40 attacks against both systems, the honest comparison is paired. If the baseline is hijacked by 6 or more attacks that HireGuard blocks, the difference is significant (exact McNemar, p = 2 × 0.5^b)."
- "Our fairness audit doesn't just say 'fair'. We planted a biased criterion and it found it, down to the exact rubric component."

## Q&A preparation

| Likely question | Answer (30 seconds or less) |
|---|---|
| Where is the AI? Isn't this an old keyword ATS? | The model reads CVs and emails in French, English and Arabic, including Derja emails, and triages the inbox [quote Hedhili's F1 per language once measured]. We deliberately don't let it decide about people. Code decides, so every point is explainable, which the EU AI Act requires for hiring tools. |
| Does your model obey injections? | Through the code path, 0 of 40 attacks moved anything (CI to 8.8%). Through the model: [Hedhili's number], or "measured tonight on the GPU; here is the method." Even a fully hijacked model can only propose typed fields, which the validator checks against visible text. |
| What if the model invents a skill? | The validator keeps a skill only if its evidence offset falls in the visible text and contains the skill's label. Invented skills are dropped and listed. |
| How do you know the ranking is fair? | Twin CVs: 0 of 89 score changes. The group audit with a planted biased criterion caught it (AIR 0.28, p = 0.005). Caveat: the data is synthetic; the audit runs on real data the same way. |
| Why not predict who accepts the offer? | Its best predictors are pay history (the EU forbids asking for it), commute (a proxy for region) and family situation (a proxy for gender). We ask for the candidate's conditions and check them against the published band instead. |
| Isn't HR Nexus employee monitoring? | No individual scores. Declared skills as counts, process times per stage, handbook questions without text or names, groups under 5 hidden. Emotion AI at work is banned in the EU, and our own experiment showed it doesn't work (AUC 0.64). |
| Doesn't human approval slow things down? | Routine items are batched; risky ones go one by one. If reviewers start missing planted test items, the batches shrink automatically. |
| Why a local model? | Candidate data stays on the customer's machine (Tunisian law 2004-63, GDPR for EU clients). The code path handles about 1,600 CVs a minute; the model's speed is [Hedhili's number]. |
| What about GDPR deletion and retention? | The talent pool expires after 2 years and can be withdrawn. Purging data after a requisition closes is on the roadmap (risk R11): we say so. |
| An SME has one HR manager. Who are the "two other approvers" for an offer? | The number of approvers is a single policy value in the code (`REQUIRED_APPROVALS`). The demo shows the strictest policy; a small company would set it to the author plus one approver (risk R14). |
| What isn't done? | Model-mode numbers (tonight), the Answer Desk, the candidate portal. Everything on the slide is measured; everything else is labelled. |
| How do you make money? | Per-company subscription; see the business slide. Pilots: [n] of [N] HR managers we interviewed asked for one. |

References for every claim: `docs/architecture.md` §11.

## Extra slides

**One platform, two modules.** Recruit (HireGuard: HR and candidates) and Team (HR Nexus: HR and staff) on one trust core: AI reads, code decides, humans approve. The only bridge is aggregate: team skill counts become a proposed rubric.

**Compliance by design.** Recruitment AI is high-risk under the EU AI Act (Annex III 4(a); obligations from 2 Dec 2027).

| Requirement | HireGuard feature |
|---|---|
| AI Act Art. 10: data governance and bias | Fairness audit with a planted-bias positive control; twins |
| Art. 12: logging | Hash-chained, anchored audit log |
| Art. 13: transparency | Evidence highlight for every score component |
| Art. 14(4)(b): automation bias | Canaries and the attention guard |
| Art. 15(5): robustness to adversarial input | Sanitizer, typed extraction, attack-success rate |
| GDPR Art. 22: no solely automated decisions | Executor returns 403 unless a human approved |
| Pay Transparency Directive 2023/970, Art. 5 | Published band, offers inside it, no pay-history questions |

**What we refuse to build.**
- Stress or emotion inference (AI Act Art. 5(1)(f); our own experiment: AUC 0.64).
- Individual performance scores.
- Culture-fit scores.
- An offer-acceptance predictor (its predictors are proxies for gender and region).
- Scraping profiles.
- Reading employees' messages.

## Business slides

**Positioning:** a secure AI HR assistant for Tunisian SMEs and ESNs. It prepares the work (screening, inbox, offers, HR answers), and a human approves every action. It runs on local GPUs, so candidate data stays in Tunisia.

**Beachhead:** IT services companies and ESNs in Grand Tunis and Sfax with 50–500 employees that hire engineers continuously (SUP'COM and ISET pipelines). Size: TBD companies (source TBD).

**Pricing hypothesis (TND, to be validated in interviews):**

| Plan | For | Price |
|---|---|---|
| Pilot | 1 open role, 3 months | TBD TND (free or nominal) |
| SME | up to 100 employees | TBD TND per month |
| Company | up to 500 employees, on-prem GPU | TBD TND per month plus setup |

Anchor: the ROI counter on the money dashboard (hours saved × the customer's own hourly cost).

**HR interview findings:** collected with [`docs/hr_interview_guide.md`](hr_interview_guide.md). Target 8–10 calls, 3+ asking for a pilot. Results: TBD (n = TBD, pilots asked = TBD).

**Roadmap:** candidate portal (magic link) → interview confirmations and rescheduling → retention purge and deletion requests → ATS integrations → INPDP compliance pack → anonymous team pulse survey (k ≥ 5).

## Ask

Pick one before stage and say it in one sentence:
- 3 pilot companies, one open role each, for 3 months; or
- GPU credits for the local model; or
- incubation.
