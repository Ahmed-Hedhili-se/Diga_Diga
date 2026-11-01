# HireGuard: Team Work Plan (4 people)

Secure AI HR System Hackathon, SUP'COM, 17 hours

> **Core principle:** the AI reads, code decides, humans approve.
> **Trust boundary:** whatever reads stranger text cannot act; whatever can act never reads stranger text.

---

## Overview

| Person | Role | Layer | Also leads |
|---|---|---|---|
| **P1** | Document pipeline | "The AI reads" | GPUs, Ollama, fallback switch |
| **P2** | Scoring & evaluation | "We prove it" | Pitch + business |
| **P3** | Workflow & security backend | "Code decides, humans approve" | Threat model in README |
| **P4** | Frontend, auth & web security | "HR sees it" | Live demo + backup video |

**Backups:** P1 ↔ P2 (extraction schema, validator) · P3 ↔ P4 (approval API contract)

---

## H0–1: All together

- [ ] Agree on JSON schemas: CV extraction, email extraction, score output, approval item, audit entry
- [ ] Freeze API contracts (endpoints, request/response shapes)
- [ ] Repo structure, branches, `.env.example`, run script
- [ ] Load the ESCO skills subset
- [ ] Warm up Ollama + Qwen3-8B on both laptops
- [ ] Agree on demo data IDs (which CVs, emails, and job offers appear in the demo)

---

## P1: Document pipeline

**Mission:** turn untrusted documents into typed, validated fields. Nothing written by a stranger passes through as free text.

### Deliverables

**1. Sanitizer (PyMuPDF)**: separate visible text from hidden content across 9 channels:
- [ ] White / near-background-color text
- [ ] Tiny fonts (below a size threshold)
- [ ] Invisible render mode (render mode 3)
- [ ] Off-page or clipped text
- [ ] Text hidden under images
- [ ] Comments, annotations, metadata
- [ ] Zero-width characters
- [ ] Homoglyphs (Cyrillic/Greek lookalikes)
- [ ] Fix hyphenation and ligatures in visible text
- [ ] Output: `visible_text`, `hidden_findings[]` (channel, text, page, bbox) for the Security Center

**2. Instruction detector (signal only, never changes a score)**
- [ ] Regexes in FR / EN / AR / Derja / Arabizi ("ignore", "score me", "evaluator note", etc.)
- [ ] Prompt Guard 2 on 512-token chunks
- [ ] Output: `injection_flags[]` with location, shown to HR

**3. Extractor (Qwen3-8B on Ollama, JSON-schema output)**
- [ ] One document per call, no tools, no memory
- [ ] Typed fields only: dates, ESCO skill IDs, evidence character offsets, degree enum, languages (ISO + CEFR)
- [ ] Email extraction: intent enum, urgency enum
- [ ] **No free-text fields anywhere in the schema**
- [ ] Retry once on schema failure, then mark as "needs human"

**4. Validator (code)**
- [ ] A skill counts only if its evidence offset falls inside visible text AND contains an ESCO label for that skill
- [ ] Years of experience computed from dates, not from model claims
- [ ] Drop any field that fails validation, and log why

**5. After H9: HR Answer Desk retrieval**
- [ ] Index the handbook PDF
- [ ] Return exact extracts with section/page citations; nothing generated
- [ ] Personal questions are routed to the HR queue (hand off to P3's queue API)

**6. Infrastructure**
- [ ] Ollama running on both GPUs, load-balanced or split by task
- [ ] Groq fallback switch (fictional data only), off by default

### Timeline
| Hours | Task |
|---|---|
| H1–5 | Sanitizer, all 9 channels |
| H5–9 | Extractor tuning, detector, validator with P2 |
| H9–12 | Answer Desk retrieval |
| H12–14 | Fix extraction failures found by P2's eval |
| H14–17 | Freeze: bug fixes, README section on pipeline |

### Hands off to
- **P2:** validated extraction JSON
- **P4:** `hidden_findings` and evidence offsets for highlighting
- **P3:** email intent/urgency fields

### Before the event
- [ ] Ollama + Qwen3-8B tested on both laptops
- [ ] Sanitizer prototype working on 5 test PDFs (one per channel family)

---

## P2: Scoring, evaluation & pitch

**Mission:** rank candidates fairly with code, prove security and quality with numbers, and own the story.

### Deliverables

**1. Scorer (code)**
- [ ] HR-written rubric format (skill weights, minimum years, degree, languages)
- [ ] Weighted score from validated fields only
- [ ] Template justifications ("Python: 4 yrs, see p.1"); no generated text
- [ ] Evidence offsets passed to P4 for click-to-highlight
- [ ] Scores shown as **proposed** until HR commits the shortlist

**2. Data**
- [ ] ESCO subset for the demo job offers
- [ ] 200 CVs generated from ground-truth JSON (FR/EN/AR mix)
- [ ] 40 in-house attacks (9 channels, FR/EN/AR)
- [ ] Sealed outsider attacks (30, written by people outside the team)

**3. Evaluation harness**
- [ ] Attack success = any field, score, rank, routing, or recipient differing from the payload-free twin
- [ ] ResumeShield benchmark (104 docs, 72 injected)
- [ ] Baseline: WithSecure/Reversec vulnerable CV screener on the same model
- [ ] Clopper-Pearson 95% intervals for k/n
- [ ] Hidden-text detection precision / recall
- [ ] Extraction F1 on the 200 CVs
- [ ] Counterfactual twins: towns (La Marsa, Sfax, Kasserine, Tataouine), schools (SUP'COM, ISET, private), 12-month gap, CV language, ingénieur/ingénieure → score must not change
- [ ] Ranking sanity vs 2 outside annotators (Kendall tau, Cohen kappa)
- [ ] Email routing accuracy on 100 emails incl. 15 spoofed (with P3)

**4. Money dashboard backend**
- [ ] Cost of vacancy per open role in TND
- [ ] Days to fill vs target
- [ ] Hours saved (CVs screened, emails drafted, documents released, questions answered)
- [ ] ROI counter with customer-entered hourly cost

**5. Pitch lead**
- [ ] Metrics slide with confidence intervals
- [ ] Business slides: positioning, beachhead, pricing hypothesis, roadmap
- [ ] HR interview findings (8–10 interviews)
- [ ] 5-minute script, timed

### Timeline
| Hours | Task |
|---|---|
| H1–5 | Scorer, validator rules with P1, rubric format |
| H5–9 | 200-CV run, F1, start eval harness |
| H9–12 | Eval runs (benchmark, baseline, twins), money backend |
| H12–14 | Metrics slide, pitch script |
| H14–17 | Freeze: README eval section, rehearse pitch ×3 |

### Hands off to
- **P4:** scores, justifications, money dashboard data
- **P1:** failing extraction cases to fix

### Before the event
- [ ] ESCO subset, 200 CVs with ground truth, 40 attacks
- [ ] Outsider attacks collected and sealed
- [ ] 8–10 HR interviews done (target: 3+ ask for a pilot)

---

## P3: Workflow & security backend

**Mission:** the only parts of the system with authority. Nothing is sent, booked, released, or recorded without a human approval.

### Deliverables

**1. Email gate (code)**
- [ ] SPF / DKIM / DMARC check with `authheaders`
- [ ] Sender must match the candidate's verified address
- [ ] Rules set `needs_human` and `suspicious`; the model never judges whether its input is an attack
- [ ] Spoofed sender → no candidate data offered

**2. Drafting**
- [ ] FR / EN / AR reply templates with typed slots only
- [ ] 3 free interview slots from the recruiter's calendar (mock calendar)
- [ ] Booking only after approval

**3. Approval service**
- [ ] Risk-scored queue
- [ ] Routine items batched (diff data for P4's view)
- [ ] Canary item planted every 20th item; track reviewer misses
- [ ] High-risk items opened one by one
- [ ] Offers require a second approver
- [ ] Approval policy enforced: every send, booking, status change, shortlist commit, document release, held-email release, leave request

**4. Executor**
- [ ] Runs approved items only
- [ ] **Unapproved send = HTTP 403** (demo moment)

**5. Audit log**
- [ ] App DB role: INSERT / SELECT only
- [ ] Trigger blocks UPDATE / DELETE
- [ ] SHA-256 hash chain
- [ ] Anchor every 30 min with OpenTimestamps + public git commit

**6. Self-service documents**
- [ ] Work certificate, salary certificate, leave confirmation generated from templates
- [ ] Released only after one HR click

**7. Interview loop closer (built, not demoed)**
- [ ] 2-minute structured scorecard backend
- [ ] Manager reminders
- [ ] (Confirmations and rescheduling → roadmap)

**8. Security owner**
- [ ] Internal pentest of P4's web app at H12–14
- [ ] README threat model mapped to OWASP LLM Top 10 2025 (LLM01, 02, 05, 06, 09, 10) + web risks

### Timeline
| Hours | Task |
|---|---|
| H1–5 | Email gate, templates |
| H5–9 | Approvals, executor (403), audit log |
| H9–12 | Anchor, documents, interview loop backend |
| H12–14 | Pentest P4's app, report findings |
| H14–17 | Freeze: README threat model, bug fixes |

### Hands off to
- **P4:** approval queue API, audit log API, document endpoints
- **P2:** email routing results for the eval

### Before the event
- [ ] Template texts in FR / EN / AR
- [ ] 100 test emails incl. 15 spoofed, with correct/incorrect DMARC headers

---

## P4: Frontend, auth & web security

**Mission:** HR opens HireGuard every morning and finds the work prepared, and the app itself is not the weak point.

### Deliverables

**1. Pages**
- [ ] Layout and navigation
- [ ] Candidates page: ranked list, click a score → evidence highlighted in the PDF
- [ ] Approval queue: batches, diff view, canaries, one-by-one high-risk items
- [ ] Inbox digest: grouped by type and urgency, "needs human" and "suspicious" lanes
- [ ] Security Center: blocked attacks with hidden text revealed, audit log view with chain status
- [ ] HR Answer Desk UI with citations
- [ ] Money dashboard UI
- [ ] Interview scorecard form

**2. Auth and access**
- [ ] Login, 4 roles: Recruiter, HR Manager, Employee, Admin
- [ ] Object-level access checks on every endpoint (no IDOR)
- [ ] No default accounts

**3. Web security**
- [ ] Output escaping everywhere (candidate text is hostile)
- [ ] Strict CSP
- [ ] Upload limits (size, type, page count)
- [ ] Rate limits
- [ ] Fix all findings from P3's pentest

**4. Demo lead**
- [ ] Seeded demo data matching the pitch script
- [ ] Click path rehearsed: CV ranking → poisoned CV → certificate → 403 → money dashboard
- [ ] Backup video recorded before H17

### Timeline
| Hours | Task |
|---|---|
| H1–5 | Layout, auth/roles, candidates page |
| H5–9 | Approval queue, inbox digest, PDF highlight |
| H9–12 | Security Center, money + Answer Desk UI, CSP |
| H12–14 | Fix pentest findings, polish |
| H14–17 | Freeze: demo ×3, backup video |

### Hands off to
- **P2:** working demo for the pitch rehearsal
- **P3:** app ready for pentest at H12

### Before the event
- [ ] UI wireframes for all pages
- [ ] Handbook PDF (fictional) and demo data set

---

## Gates

| Gate | Condition | If it fails |
|---|---|---|
| **H9** | CV → sanitize → extract → validate → score → evidence → approve → send works end to end | Everyone joins the broken step; cut H9–12 extras starting with the interview loop |
| **H12** | Eval numbers in, pentest started | Use partial results with honest k/n; drop lowest-priority UI page |
| **H14** | Freeze | Bug fixes only, no new features |

**Rule:** if a task is more than 1 hour behind at a gate, its backup joins, and the slower person's lowest-priority item is cut.

---

## Moved because we are 4

- Interview loop closer → built, not demoed (scorecard + reminders only)
- Candidate portal (magic link) → roadmap; demo uses pre-verified addresses (stated in README)
- Attack-us QR page → cut
- Outsider attacks and HR interviews → must be done before H0

---

## Final deliverables checklist

- [ ] Source code (repo, run script, `.env.example`)
- [ ] README: setup, architecture, pipeline (P1), threat model (P3), evaluation (P2), known limits
- [ ] 5-minute pitch + demo, rehearsed 3 times
- [ ] Backup demo video
