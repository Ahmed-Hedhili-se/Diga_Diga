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
| R1 | **P2** | `eval/render.py`, channel `under_image`: pass `keep_proportion=False` to `page.insert_image(...)`. Today the cover image becomes a 20x20 square, so most of the hidden payload stays plain visible text (ATK-005 gets no finding, ATK-023 only a low one). With the fix the sanitizer flags both as high (checked on rebuilt copies). Regenerate the corpus after the change: `cd hireguard/eval && python gen_attacks.py` | Detection check shows 38/40 only because of this | open |

---

## 2. What you can use from P1

- `HiddenFinding.severity` (`"high"` or `"low"`, default `"high"`): `low` only for undecodable glyphs (text starts `[N undecodable glyphs]`). Real zero-width, bidi, tag characters and every other channel are `high`. P3's risk score already reads it.
- `python scripts/check_detection.py` (from `hireguard/backend`): hidden-text detection check on the 40 attacks and 40 clean twins. Sanitizer only, no model.

---

## 3. P1 progress

| Task | What | Status |
|---|---|---|
| T1 | `severity` on hidden findings (H1) + detection check script | **done** |
| T2 | Portable font lookup for the demo PDFs | **done** |
| T3 | Answer Desk: BM25 search, personal-question router, route (H2) | todo |
| T4 | Offline email mode `HG_EXTRACT_MODE=ground_truth` (H11) | todo |
| T5 | `support: listed_only / dated_experience` on skills | todo |
| T6 | `docs/pipeline.md` + `docs/demo_p1.md` (H3) | todo |
| T7 | Real model on Modal (Ollama + Qwen3-8B), eval runner, security notes | todo |

## 4. Blocked

(none)

## 5. Changelog

- **2026-10-31 · Step 0**: baseline run, 187 passed + 1 expected failure. Created this file.
- **2026-10-31 · T1**: `HiddenFinding.severity`; the sanitizer now emits separate findings for real invisible characters (high), tag characters (high) and undecodable glyphs (low). 8 tests in `tests/test_severity.py`, including P3's `count_high_findings` (low-only gives 0). `scripts/check_detection.py`: **attacks with a high finding 38/40, clean twins with a high finding 0/40**. The 2 misses (ATK-005, ATK-023, channel `under_image`, Arabic payloads) are a flaw in the generated test PDFs, not in the sanitizer: see R1. H1 closed in `person3.md`.
- **2026-10-31 · T2**: `pipeline/fonts.py` (`find_unicode_font`, `require_unicode_font`, `FontNotFound`): Arial on Windows, DejaVu Sans on Linux, Arial Unicode on macOS. `pipeline/demo.py` uses it and now raises a clear error instead of silently falling back to the built-in `helv` font (no Arabic glyphs). 6 tests in `tests/test_fonts.py`. Linux install hint: `apt install fonts-dejavu-core`.
