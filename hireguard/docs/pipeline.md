# Document pipeline

Owners: Rayen (code), Hedhili (model and detector quality). Written from the module docstrings in `backend/app/pipeline/` on 31 Oct; the code is the source of truth.

```
PDF (untrusted)
  → service.check_upload    ≤ 5 MB, ≤ 6 pages, a real PDF
  → sanitizer.sanitize      visible_text + hidden_findings (8 finding types; annotations and
                            metadata share one, so the 9 attack channels are all covered)
  → detector.detect         instruction flags: a SIGNAL for HR, never changes a score
  → extractor.extract_cv    Qwen3-8B, typed JSON with line numbers, no tools, 1 retry
  → validator.validate      every claim checked against visible_text; unproven claims dropped and logged
  → scoring.scorer.score    deterministic rubric → a *proposed* score
  → persisted + audited     pipeline.process_cv
```

## Sanitizer: what a human sees vs. everything else

Visibility is decided per character from rendering facts, never from the words.

**Per character:**

| Channel | Rule |
|---|---|
| `invisible_render` | Render mode 3 or zero opacity |
| `off_page` | Outside the crop box (or the media box) |
| `tiny_font` | Font size below 4 pt (`TINY_FONT_PT`) |
| `under_image` | An image or opaque fill is drawn on top of it later in the content stream |
| `white_text` | Contrast against the background below 1.6 (`MIN_CONTRAST`; readable body text is at least 4.5) |

**On the visible text:**

| Channel | Rule |
|---|---|
| `zero_width` | Zero-width, bidi-control and Unicode tag characters are removed; tags are decoded and reported |
| `homoglyph` | Cyrillic, Greek and maths lookalikes inside Latin words are mapped to Latin and reported |

**At document level:**

| Channel | Rule |
|---|---|
| `annotation_metadata` | Annotations, form values, metadata fields, XMP description, embedded files |

Hyphenation and ligatures are repaired in `visible_text`. Hidden content is kept, up to 2,000 characters per finding, so HR can see it in the Security Center.

## Detector: a signal, not a control

Regex rules run on folded text: lower case, no diacritics, unified Arabic letters, homoglyphs mapped (`textnorm.fold_with_map`, which keeps offsets back to the original). They cover `visible_text` and every hidden finding. Prompt Guard 2 is optional (`HG_PROMPT_GUARD=1`).

Known misses on the in-house corpus (risk R2): English "Evaluator note" 4/4, Derja 3/3, Arabic 3/4. A miss does not change any score, because the detector never feeds the scorer.

## Extractor: the only place the model runs on a CV

- The model sees the visible text as **numbered lines** (at most 500 lines of 160 characters) and answers with line numbers. It never counts characters. Code turns line numbers into spans.
- ESCO skill ids are an enum in the output schema, so the model cannot invent a skill id.
- Transport (`llm.py`): Ollama, round-robin over `HG_OLLAMA_URLS`. No tools, no memory, no conversation: one system prompt and one data block per call. Groq fallback is off by default and for fictional data only.
- On schema failure the call is retried once. If it fails twice, the CV is `needs_human`.

## Validator: code checks every claim

| Claim | Kept only if |
|---|---|
| Skill | Known ESCO id; evidence span inside `visible_text`; the span contains an ESCO label of that skill |
| Experience | Valid dates, not in the future, start year written near the evidence; total years = merged intervals |
| Years per skill | Union of the valid experiences that list the (validated) skill |
| Degree | Valid evidence span with a diploma keyword of that level written there |

Everything dropped is listed (`validated.dropped`) and shown in the candidate panel.

## Measured (oracle mode, 31 Oct)

| What | Result |
|---|---|
| Hidden content found | 40/40 attacks, 0 false alarms on 40 clean twins |
| Instructions flagged | 18/28 |
| Attacks that moved a field or score, code path | 0/40 |

Model-mode results: see `docs/evaluation.md` once Hedhili's run lands (risk R1).
