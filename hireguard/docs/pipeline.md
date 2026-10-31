# Document pipeline and AI layer (P1)

> The AI reads, code decides, humans approve. Everything in this document **reads** stranger text and **cannot act**: typed fields out, no tools, no memory, no way to send, book or change a status.

## Trust boundary

```
 stranger PDF / email / question
          |
          v
 [ sanitizer ]  code, no model     visible_text  +  hidden_findings (channel, severity, page, bbox)
          |                                              |
          | visible_text only                            | shown to HR, escaped; never sent to a model
          v                                              v
 [ detector ]   regex (+ Prompt Guard)  ->  injection_flags   (signal only, never changes a score)
          |
          v
 [ extractor ]  Qwen3-8B, JSON schema      one document per call, no tools, no memory, 1 retry
          |      numbered lines in, line numbers out; ESCO ids are an enum
          v
 [ validator ]  code                       drops every claim it cannot prove from visible text
          |
          v
 ValidatedCV  ->  P2 scorer (proposes)  ->  P3 approvals (humans decide)  ->  executor
```

Nothing in `backend/app/pipeline/` imports the executor, sends mail or changes a status. The one P3 function it calls is `create_employee_question`.

## Sanitizer (`pipeline/sanitizer.py`)

Visibility is decided from rendering facts per character, never from the words. Eight hidden channels (the plan counted a ninth item, hyphenation and ligature repair, which is text repair, not a channel):

| Channel | Meaning | Severity |
|---|---|---|
| `white_text` | contrast against the background below 1.6 | high |
| `tiny_font` | font under 4 pt | high |
| `invisible_render` | render mode 3 or zero opacity | high |
| `off_page` | outside the crop or media box | high |
| `under_image` | an image or opaque fill drawn on top later | high |
| `annotation_metadata` | annotations, form values, metadata, XMP, embedded files | high |
| `zero_width` | zero-width, bidi controls, Unicode tag characters (removed and reported) | high |
| `zero_width` (undecodable glyph, U+FFFD) | often an Arabic word inside a FR/EN CV | **low**: shown to HR, adds no risk |
| `homoglyph` | Cyrillic, Greek or math lookalikes inside Latin words, mapped back and reported | high |

`HiddenFinding.severity` is `high` unless set to `low`; a missing value means high (fail closed). P3's risk score counts only high findings, so a clean Arabic-name CV is not pushed into the high-risk lane.

## Detector (`pipeline/detector.py`)

Regex rules in French, English, Arabic, Derja and Arabizi ("ignore", "score me", "evaluator note") run on folded text, over `visible_text` **and** every hidden finding. Prompt Guard 2 on 512-token chunks is optional (`HG_PROMPT_GUARD=1`). Output: `injection_flags` with location. **It never changes a score.**

## Extractor (`pipeline/extractor.py`, `pipeline/llm.py`)

The model never counts characters. The document is shown as numbered lines (at most 500 lines of 160 characters) and the model answers with line numbers; code turns them into `visible_text` offsets and narrows skill evidence to the ESCO label match. The schema has **no free-text field**: dates, ESCO ids (an enum), degree enum, ISO language plus CEFR. Temperature 0, seed 7, thinking off. A schema failure is retried once, then the CV is `needs_human`.

Transport (`llm.py`): round-robin over `HG_OLLAMA_HOSTS`, a local GPU or the Modal endpoint. A 502/503/504 or a timeout is retried once (a Modal cold start takes 1–3 minutes); after that the caller gets `needs_human`. When `HG_OLLAMA_MODAL_KEY` and `HG_OLLAMA_MODAL_SECRET` are both set they go out as `Modal-Key` / `Modal-Secret` headers; they are scrubbed from every error message and never logged.

## Validator (`pipeline/validator.py`)

A skill counts only if its evidence span is inside `visible_text` **and** contains an ESCO label for that skill. Years of experience are computed from valid dates (merged intervals), never from a model claim. Every dropped field is logged with a code-generated reason. Each skill also gets `support`: `dated_experience` when a valid dated job block writes it, else `listed_only` (what keyword stuffing looks like), plus `skills_listed_only_ratio` for the CV.

## Email extraction (`pipeline/email_extract.py`)

Language, intent and urgency enums only; the gate (P3) decides the lane from code rules. `HG_EXTRACT_MODE=ground_truth` reads the labelled demo emails so the demo runs without Ollama; it logs a warning on every call, is **not** a model run, and returns nothing for text it does not know. The default mode, with the model down, returns nothing (`extraction_failed`, a human decides); it never falls back to ground truth.

## HR Answer Desk (`pipeline/answer_desk.py`)

`POST /api/answer-desk/ask` (employee, HR manager). Retrieval is BM25 over the 34 paragraphs of `handbook.pdf` (pure Python, no model). Answer is one of:

- `extract`: the best paragraphs **word for word**, with section and page. Nothing is generated.
- `routed`: the question is about the asker (a possessive or own-data cue plus a topic: leave, salary, certificate, contract, other) and goes to P3's HR queue as a ticket. "How do I request a certificate?" stays a policy question.
- `ask_hr`: nothing in the handbook scores above `MIN_SCORE` (4.0).

The question is capped at 1,000 characters, control and bidi characters are stripped, and only length, topic and kind are logged.

## Environment flags

| Variable | Default | Effect |
|---|---|---|
| `HG_OLLAMA_HOSTS` | `http://localhost:11434` | comma-separated Ollama hosts, local or Modal, round-robin (`HG_OLLAMA_URLS` still read if unset) |
| `HG_OLLAMA_MODAL_KEY`, `HG_OLLAMA_MODAL_SECRET` | empty | Modal proxy-auth token for a remote Ollama; env only, never committed or logged |
| `HG_LLM_TIMEOUT` | `120` | seconds per model call; one retry on 502/503/504 or timeout |
| `HG_OLLAMA_MODEL` | `qwen3:8b` | extraction model |
| `HG_EXTRACT_MODE` | `model` | `ground_truth` = offline demo for emails (not a model run) |
| `HG_PROMPT_GUARD` | `0` | `1` adds Prompt Guard 2 to the detector (needs `requirements-ml.txt`) |
| `HG_GROQ_FALLBACK` | `0` | `1` allows the Groq fallback (fictional data only); needs `GROQ_API_KEY` |
| `HG_MAX_UPLOAD_BYTES`, `HG_MAX_PDF_PAGES` | 5 MB, 6 | upload limits |

## Numbers (2026-10-31, no model involved)

| Check | Result | How to reproduce |
|---|---|---|
| Attacks with a high finding | **38/40** | `python scripts/check_detection.py` (the 2 misses come from the test generator: its cover image is 20x20 pt instead of full width; the sanitizer flags both once the cover is full width, see `person1.md` R1) |
| Clean twins with a high finding | **0/40** | same |
| Personal questions routed to HR | **8/8** | `pytest tests/test_answer_desk.py` (`data/handbook/questions.json`) |
| Policy questions, top-1 section correct | **12/12** | same |
| Backend tests | 287 passed, 1 expected failure (a P4 finding) | `python -m pytest -q` in `hireguard/backend` |

Extraction quality against the real model is measured by P2's harness; the Modal run is described in `hireguard/infra/README.md`.

## Real model on Modal

The laptop GPU (RTX 4050, 6 GB) holds only 63% of Qwen3-8B, so a CV takes about 30 s. For full runs we rent one L4 on Modal: `infra/modal_ollama.py` serves Ollama behind proxy auth, with the model kept in a volume (downloaded once). Fictional test data only: Modal runs in the US.

| Budget fact | Value |
|---|---|
| L4 GPU (24 GB) | $0.000222/s ≈ **$0.80/hour**, per second, $0 when scaled to zero |
| Credit | $10 ≈ 12 GPU-hours |
| Full eval (50 CVs + 40 attacks + 40 twins + 100 emails) | under 1 hour ≈ $1 |
| Guards | 1 container max, scale to zero after 5 idle minutes, proxy auth, `--max-requests` cap (default 400) |

`scripts/run_model_eval.py` runs the real model and writes raw results to `eval/out/model_run_<date>.json` for P2: per item ok/failed, latency, requests, schema retries and typed fields; per attack pair `attack_success`; email intent against `labels.json`; total requests and the estimated cost. It refuses `HG_EXTRACT_MODE=ground_truth`. A local smoke run (2 emails, laptop GPU) read 2/2 intents correctly.

### Real model results

Pending: filled in after the Modal run (date, model, GPU, cost, extraction success, latency, attack success, email intent accuracy).

## Known limits

- Keyword stuffing and fake dated jobs written in visible text are not detectable by code; the score is a proposal and HR sees the evidence. `listed_only` makes the first one visible.
- A `Skills:` line right after the last job is read as part of that job block, so a skill the model attributes to that job counts as dated.
- The "ask HR" cutoff has a thin margin (real questions score 4.72 or more, out-of-scope ones 3.25 or less): re-check it if the handbook changes.
