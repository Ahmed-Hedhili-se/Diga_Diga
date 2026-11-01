# HireGuard: 5-minute pitch (1 Nov)

> Rules for every number on stage:
> - It comes from `eval/results/*.json` (also on Security Center → Evaluation, with its mode) or the HR interview notes, as k/n with its 95% interval.
> - A row still marked **TBD** one hour before the pitch is cut, not guessed.
> - Oracle (code-path) results are never presented as model results.
>
> The click path, accounts and backup plan are in [`demo_script.md`](demo_script.md), the only demo script.

## Script (5:00)

| Time | Slide | Say | On screen |
|---|---|---|---|
| 0:00–0:25 | Hook | "An HR assistant in Sfax gets 300 CVs for one Data Engineer job. Researchers scanned 197,000 real CVs this year: about one in a hundred hides text meant only for the AI (USENIX Security 2026). We took 40 such attacks to a standard AI screener: 13 moved its score." | Title, then one CV with its white text revealed |
| 0:25–0:50 | Problem | "HR teams spend the day sorting, replying and chasing; a hire takes 39 days at the median in SHRM's benchmark. AI agents can do this work, but they read strangers' text *and* they can act. That combination is the vulnerability." | Problem slide: [TBD from the interviews] minutes per CV, 39-day median |
| 0:50–1:15 | Principle | "HireGuard: the AI reads, code decides, humans approve. One trust core, two modules: Recruit for candidates, Team for staff." | Architecture diagram (`docs/architecture.md` §1) |
| 1:15–1:45 | Demo | "Here is the poisoned CV." The hidden text is revealed; the score did not move. Click a score: every point is highlighted in the CV. | Demo steps 1–2 |
| 1:45–2:05 | Demo | "These two are tied. Any ranker picks one by sort order. We flag it as borderline and leave it to a human." | Demo step 3 |
| 2:05–2:30 | Demo | "Before the interviews: CAND-002 wants 4,600; the published band stops at 3,800. We don't predict who will accept: we ask, and we check. The offer is drafted inside the band and waits for two HR managers." | Demo step 4 |
| 2:30–2:50 | Demo | "Nothing leaves without a human." Run an unapproved item: **403**. "And if reviewers start rubber-stamping, the batches shrink." | Demo step 5 |
| 2:50–3:15 | Demo | "HR Nexus: the data team has nobody with Spark, so the hiring rubric proposes it. Employees ask most about remote work. We measure the process and the handbook, never the people." | Demo step 6 |
| 3:15–3:55 | Proof | "Same model, same 40 attacks: the standard screener moved on 13, HireGuard on 3, and only one of those 3 helped the attacker, by 1.4 points. Paired, that difference is significant: p = 0.006." Then one limit, said plainly: the twin result below. | Metrics slide |
| 3:55–4:35 | Business | Beachhead, pricing, pilots asked, then one line on compliance: "built to the EU AI Act, which ESNs serving EU clients will need". | Business slide, compliance table |
| 4:35–5:00 | Close | "What we refuse to build: emotion AI, performance scores, culture fit. HireGuard does the paperwork; people decide about people." Then the ask. | Refuse-to-build slide, then the ask |

Money dashboard, employee documents and follow-ups are cut from the live demo. Mention them in one line if time allows.

## Metrics slide

Two kinds of numbers, never mixed. **Model** = the real Qwen3-8B, run on 31 Oct **before identity masking** (`eval/results/summary_unmasked_qwen3-8b.json`, `baseline.json`). **Code path** = ground-truth extraction, no model (`summary_oracle.json`).

| Claim | HireGuard | Standard screener (same model) |
|---|---|---|
| Attacks that moved a field, score or rank (model) | **3/40** (7.5%, CI 1.6–20.4%); 1 raised the score (+1.4 points), 2 lowered it | **13/40** (32.5%, CI 18.6–49.1%); 4/40 raised it by 10+ points |
| Paired comparison, same 40 attacks | 11 attacks moved only the screener, 1 only HireGuard: **exact McNemar p = 0.006** | |
| Attacks that moved anything (code path) | 0/40 (CI 0.0–8.8%) | — |
| Hidden-text detection (sanitizer, no model) | 40/40 found, 0 false alarms on 40 clean twins | — |
| Email routing (model, 100 emails, 15 spoofed) | right lane 100/100; spoofed emails given no candidate data 15/15; unsafe routing 0/100 | — |
| Fairness audit catches a planted biased criterion | yes: adverse-impact ratio 0.28, p = 0.005; gap traced to the degree component | — |
| 300 CVs through pipeline and database (code path) | 0 errors, p95 45 ms per CV | — |
| **Known limit:** score changed when only town, school, gap, language or gendered title changed (model) | **26/90** (28.9%, CI 19.8–39.4%), 14/20 for language swaps. Code path: 0/89. Masking of identity fields was added after this run; its number comes from Hedhili's re-run | — |
| Extraction F1 (model) | TBD: measured on 2 CVs only, which supports no claim | — |

Footnote on the slide: "Clopper-Pearson 95% intervals; n shown for every rate. Fictional CVs and emails."

Two claims to say out loud:

- "We don't say 'attacks never work'. On the same 40 attacks and the same model, the standard screener moved 13 times and HireGuard 3, and the paired test says that's no accident (p = 0.006)."
- "We also show where we fail: the model's reading still changed scores between twin CVs. That's why we mask identity fields now, and why our fairness audit exists: we planted a biased criterion and it found it, down to the rubric component."

## Q&A preparation

| Likely question | Answer (30 seconds or less) |
|---|---|
| Where is the AI? Isn't this an old keyword ATS? | The model reads CVs and emails in French, English and Arabic: it routed 100 of 100 test emails (51 French, 35 English, 14 Arabic) to the right lane. We deliberately don't let it decide about people. Code decides, so every point is explainable, which the EU AI Act requires for hiring tools. |
| Does your model obey injections? | Sometimes, and we measured it: 3 of 40 attacks moved HireGuard's output, and only one in the attacker's favour, by 1.4 points. A standard screener on the same model moved on 13. Even a fully hijacked model only proposes typed fields, which code checks against the visible text. |
| What if the model invents a skill? | The validator keeps a skill only if its evidence falls in the visible text and contains the skill's label. Invented skills are dropped and listed. |
| How do you know the ranking is fair? | Not yet well enough, and we say so: through the model, 26 of 90 twin CVs changed score, mostly when the CV language changed. We now mask identity fields before the model reads a CV and re-measure. The group audit catches a planted biased criterion (AIR 0.28, p = 0.005). |
| Why not predict who accepts the offer? | Its best predictors are pay history (the EU forbids asking for it), commute (a proxy for region) and family situation (a proxy for gender). We ask for the candidate's conditions and check them against the published band instead. |
| Isn't HR Nexus employee monitoring? | No individual scores. Declared skills as counts, process times per stage, handbook questions without text or names, groups under 5 hidden. Emotion AI at work is banned in the EU, and our own research showed stress prediction from work data is weak (AUC 0.64). |
| Doesn't human approval slow things down? | Routine items are batched; risky ones go one by one. If reviewers start missing planted test items, the batches shrink automatically. |
| Where does the model run? | Locally by default: Ollama on the customer's own machine, so candidate data can stay in Tunisia (law 2004-63; GDPR for EU clients). For the hackathon we also deployed it on a rented cloud GPU, with fictional data only. Speed: the code path handles about 1,600 CVs a minute; the model takes about 40 seconds per CV on the hardware we measured. |
| What about GDPR deletion and retention? | The talent pool expires after 2 years and can be withdrawn. Purging data after a requisition closes is on the roadmap (risk R11): we say so. |
| An SME has one HR manager. Who are the "two other approvers" for an offer? | The number of approvers is one policy value in the code (`REQUIRED_APPROVALS`). The demo shows the strictest policy; a small company would use the author plus one approver (risk R14). |
| What isn't done? | Model numbers after masking (re-run in progress), extraction quality on a large sample, the candidate portal. Everything on the slide is measured; everything else is labelled. |
| How do you make money? | Per-company subscription; see the business slide. Pilots: [n] of [N] HR managers we interviewed asked for one. |

References for every claim: `docs/architecture.md` §11.

## Extra slides

**One platform, two modules.** Recruit (HireGuard: HR and candidates) and Team (HR Nexus: HR and staff) on one trust core: AI reads, code decides, humans approve. The only bridge is aggregate: team skill counts become a proposed rubric.

**Compliance by design.** Recruitment AI is high-risk under the EU AI Act (Annex III 4(a); obligations from 2 Dec 2027).

| Requirement | HireGuard feature |
|---|---|
| AI Act Art. 10: data governance and bias | Fairness audit with a planted-bias positive control; twins; identity masking |
| Art. 12: logging | Hash-chained, anchored audit log |
| Art. 13: transparency | Evidence highlight for every score component |
| Art. 14(4)(b): automation bias | Canaries and the attention guard |
| Art. 15(5): robustness to adversarial input | Sanitizer, typed extraction, measured attack success vs. a standard screener |
| GDPR Art. 22: no solely automated decisions | Executor returns 403 unless a human approved |
| Pay Transparency Directive 2023/970, Art. 5 | Published band, offers inside it, no pay-history questions |

**What we refuse to build.**
- Stress or emotion inference (AI Act Art. 5(1)(f); our own research: AUC 0.64).
- Individual performance scores.
- Culture-fit scores.
- An offer-acceptance predictor (its predictors are proxies for gender and region).
- Scraping profiles.
- Reading employees' messages.

## Business slides

**Positioning:** a secure AI HR assistant for Tunisian SMEs and ESNs. It prepares the work (screening, inbox, offers, HR answers), and a human approves every action. The model runs locally by default, so candidate data can stay in Tunisia, and it can import applicants from Odoo and mirror approved actions back to it.

**Beachhead:** IT services companies and ESNs in Grand Tunis and Sfax with 50–500 employees that hire engineers continuously (SUP'COM and ISET pipelines). Size: TBD companies (source TBD).

**Pricing hypothesis (TND, to be validated in interviews):**

| Plan | For | Price |
|---|---|---|
| Pilot | 1 open role, 3 months | TBD TND (free or nominal) |
| SME | up to 100 employees | TBD TND per month |
| Company | up to 500 employees, on-prem GPU | TBD TND per month plus setup |

Anchor: the ROI counter on the money dashboard (hours saved × the customer's own hourly cost).

**HR interview findings:** collected with [`hr_interview_guide.md`](hr_interview_guide.md). Target 8–10 calls, 3+ asking for a pilot. Results: TBD (n = TBD, pilots asked = TBD).

**Roadmap:** candidate portal (magic link) → interview confirmations and rescheduling → retention purge and deletion requests → ATS integrations → INPDP compliance pack → anonymous team pulse survey (k ≥ 5).

## Ask

Pick one before stage and say it in one sentence:
- 3 pilot companies, one open role each, for 3 months; or
- GPU credits for the local model; or
- incubation.
