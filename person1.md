# Person 1 (P1): document pipeline and AI layer, report for the team

> The AI reads, code decides, humans approve.
> P1 owns everything that reads stranger text: sanitizer, detector, extractor, validator, email extraction, Answer Desk.
> None of it can act. Typed fields out, no tools, no memory.
> This file is updated after every P1 task. **Section 1 is what I need from you.**

Last update: 2026-10-31 · branch `hedhili` · backend tests: 187 passed + 1 expected failure (P4's finding F5)

---

## 1. What I need from you

| # | For | Request | Why | Status |
|---|---|---|---|---|
| R3 | **P2** | `ValidSkill.support` is now `"dated_experience"` or `"listed_only"`, and `ValidatedCV.skills_listed_only_ratio` is the share of listed-only skills. Please weight a `listed_only` skill at **0.3 or less** of a `dated_experience` one in the skills component, and add a justification line like "Python: listed only, no dated job (see p.1)". Your scorer and rubric are untouched by me | Keyword stuffing earns little | open |
| R4 | **P4** | Candidate detail: show a small "listed only" badge on a skill when `support == "listed_only"`, and the ratio (for example "8 of 9 skills listed only") near the score. Old stored records have no field and read as `listed_only`, so re-run the seed after pulling | Make stuffing visible to HR | **done (P4)**: skills list with a "listed only" / "backed by a dated job" badge, and "N of M skills listed only" under the score |
| R2 | **P4** | Answer Desk page: `POST /api/answer-desk/ask` `{question}` now answers with `kind`: **`extract`** (show `extracts[]`, each `{text, section, section_id, page}`, as quotes with "Handbook, <section>, p.<page>"; text is plain, escape it), **`routed`** (show "Sent to HR, ticket <ticket_id>"; the question is in P3's queue), **`ask_hr`** (show `message`; no extra call needed, the user can re-ask in the personal form). Max 1000 characters, 422 above. Contract row in `contracts/API.md` updated | New response shapes | **done (P4)**: `extract` as quotes "Handbook, section, p.N", `routed` with the ticket (and "My questions" refreshes), `ask_hr` shows the message and a "Send this question to HR" button; 1000 chars |
| R1 | **P2** | `eval/render.py`, channel `under_image`: pass `keep_proportion=False` to `page.insert_image(...)`. Today the cover image becomes a 20x20 square, so most of the hidden payload stays plain visible text (ATK-005 gets no finding, ATK-023 only a low one). With the fix the sanitizer flags both as high (checked on rebuilt copies). Regenerate the corpus after the change: `cd hireguard/eval && python gen_attacks.py` | Detection check shows 38/40 only because of this | open |

---

## 2. What you can use from P1

- `HiddenFinding.severity` (`"high"` or `"low"`, default `"high"`): `low` only for undecodable glyphs (text starts `[N undecodable glyphs]`). Real zero-width, bidi, tag characters and every other channel are `high`. P3's risk score already reads it.
- `POST /api/answer-desk/ask` (roles E, M): `extract` | `routed` | `ask_hr`, see R2. Code: `pipeline/answer_desk.py` (`search`, `personal_topic`, `route_personal`, `answer`). Question set: `data/handbook/questions.json` (20 questions, 8 personal).
- `HG_EXTRACT_MODE=ground_truth` (env): the email extractor returns the labelled intent, language and urgency of the 100 demo emails, looked up by body text. For the demo without Ollama. It logs a warning on every call and is **not** a model run. Default (unset or `model`) is unchanged.
- `ValidSkill.support` and `ValidatedCV.skills_listed_only_ratio` (additive; defaults `listed_only` / `0.0`).
- `python scripts/check_detection.py` (from `hireguard/backend`): hidden-text detection check on the 40 attacks and 40 clean twins. Sanitizer only, no model.

---

## 3. P1 progress

| Task | What | Status |
|---|---|---|
| T1 | `severity` on hidden findings (H1) + detection check script | **done** |
| T2 | Portable font lookup for the demo PDFs | **done** |
| T3 | Answer Desk: BM25 search, personal-question router, route (H2) | **done** |
| T4 | Offline email mode `HG_EXTRACT_MODE=ground_truth` (H11) | **done** |
| T5 | `support: listed_only / dated_experience` on skills | **done** |
| T6 | `docs/pipeline.md` + `docs/demo_p1.md` (H3) | **done** |
| T7 | Real model on Modal (Ollama + Qwen3-8B), eval runner, security notes | todo |

## 4. Blocked

(none)

## 4b. Known limits of my layer

- **Job blocks swallow a trailing skills list.** The validator reads a job block from its heading to the next job or 600 characters. A `Skills:` line right after the *last* job is therefore inside that block, so a skill the extractor attributes to that job counts as `dated_experience` even if it was only in the list. It affects years and `support` alike. I did not change the rule (it moves P2's scores); a fix would cut the block at a section heading such as Skills, Compétences, Education. Decide after the Modal results.

## 5. Changelog

- **2026-10-31 · Step 0**: baseline run, 187 passed + 1 expected failure. Created this file.
- **2026-10-31 · T1**: `HiddenFinding.severity`; the sanitizer now emits separate findings for real invisible characters (high), tag characters (high) and undecodable glyphs (low). 8 tests in `tests/test_severity.py`, including P3's `count_high_findings` (low-only gives 0). `scripts/check_detection.py`: **attacks with a high finding 38/40, clean twins with a high finding 0/40**. The 2 misses (ATK-005, ATK-023, channel `under_image`, Arabic payloads) are a flaw in the generated test PDFs, not in the sanitizer: see R1. H1 closed in `person3.md`.
- **2026-10-31 · T2**: `pipeline/fonts.py` (`find_unicode_font`, `require_unicode_font`, `FontNotFound`): Arial on Windows, DejaVu Sans on Linux, Arial Unicode on macOS. `pipeline/demo.py` uses it and now raises a clear error instead of silently falling back to the built-in `helv` font (no Arabic glyphs). 6 tests in `tests/test_fonts.py`. Linux install hint: `apt install fonts-dejavu-core`.
- **2026-10-31 · T3 (Answer Desk, 3 commits)**: (a) BM25 over the 34 handbook paragraphs read from `handbook.pdf` (exact text, real page), FR/AR/Derja words bridged to English by a synonym map; (b) personal router in code: a possessive or own-data cue plus a topic word means personal and goes to P3's queue, a how-to phrasing stays a policy question; (c) the route: 1000-character cap (422), control and bidi characters stripped, only length, topic and kind logged. `MIN_SCORE = 4.0`: real questions score 4.72 or more, out-of-scope ones 3.25 or less (the margin is thin, so a new handbook needs a re-check). **Numbers on the 20 questions: personal routing 8/8, policy top-1 12/12 (needs at least 80%).** 49 tests in `tests/test_answer_desk.py`. H2 closed in `person3.md`.
- **2026-10-31 · T4**: `email_extract.extract_email` honours `HG_EXTRACT_MODE`. `ground_truth` looks the email up by its body text in the shipped `.eml` fixtures (the gate calls the extractor with the body only, so there is no id to look up); text it does not know returns `None` = needs human, nothing is invented. Default mode with Ollama down still returns `None` (`extraction_failed`), never ground truth. Two pairs of emails have word-for-word the same text but different urgency labels (EML-002/012/040, EML-052/074), so those return the higher urgency. 11 tests in `tests/test_email_offline.py`, including the gate end to end (EML-002 gives a routine draft offline; the spoof EML-011 stays suspicious). H11 closed in `person3.md`.
- **2026-10-31 · T5**: each validated skill gets `support` (`dated_experience` if a valid dated job block writes the skill, else `listed_only`) and the CV gets `skills_listed_only_ratio`. A stuffed skills list gives a ratio of 1.0; 2 of 5 skills backed by a job gives 0.4; a job that fails validation backs nothing. Old stored records still load. 5 tests in `tests/test_support.py`. Known limit recorded in section 4b. Hand-offs R3 (P2) and R4 (P4).
- **2026-10-31 · T6**: `hireguard/docs/pipeline.md` (trust boundary, the sanitizer channels with severities, detector, extractor, validator, email extraction, Answer Desk, env flags, numbers, known limits) and `hireguard/docs/demo_p1.md` (5 steps, checked against the seeded data: CAND-006 shows `white_text` + `tiny_font`, CAND-004 shows one low finding). README link restored. H3 closed in `person3.md`.
