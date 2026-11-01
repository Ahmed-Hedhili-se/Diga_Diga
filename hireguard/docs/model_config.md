# Model configuration and hand-off (Hedhili to Rayen)

What the extraction model is, how it runs, what it may return, and how it fails. Measured results are in
[evaluation.md](evaluation.md); this file records the setup so a run can be repeated and compared.

## Configuration record

| Item | Value | Source |
|---|---|---|
| Model | `qwen3:8b` (Qwen3 8.2B parameters) | `HG_OLLAMA_MODEL` |
| Digest | `500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41` (5.2 GB) | Ollama `/api/tags`, 1 Nov 2026 |
| Format and quantization | GGUF, `Q4_K_M` | Ollama `/api/show` |
| Runtime | Ollama 0.40.13 | Ollama `/api/version` |
| Where it ran | Modal, one NVIDIA **L4** (24 GB), US region, app `hireguard-ollama` | `infra/modal_ollama.py` |
| Model context | 40960 tokens; we request `num_ctx` 8192 | `backend/app/pipeline/llm.py` |
| Sampling | `temperature` 0, `seed` 7, `think` false, JSON-schema constrained output (`format`) | `llm.py` |
| Keep-alive | 10 min; the container scales to zero after 5 idle minutes; `max_containers=1` | `infra/modal_ollama.py` |
| Access | Modal proxy auth (`Modal-Key` / `Modal-Secret`); the key and secret are read from the environment and scrubbed from errors | `llm.py` |

Ollama's own default sampling for this model is `temperature` 0.6, `top_k` 20, `top_p` 0.95. We override
`temperature` and `seed` on every request, so results are repeatable on the same weights and runtime. A different
GPU or Ollama version can still change numeric results slightly, which is why the eval caches by exact prompt.

To record these again after a model or runtime change: `/api/version`, `/api/tags`, `/api/show` on the endpoint.

## Isolation (what the model cannot do)

- One system prompt and one data block per call. No conversation history, no memory across documents, no tools,
  no function calling, no network or database access from the model. The prompt is built in
  `extractor.render_document`; the CV is wrapped as numbered lines inside `<document>`, and any `<document>` tag
  in the CV is neutralised.
- The output is JSON constrained by a schema and then parsed into `CVExtraction`
  (`backend/app/contracts.py`). That type has **no free-text field**: only ESCO ids, line numbers, `YYYY-MM`
  dates, degree level, language ISO and CEFR level. Evidence spans are computed by our code from line numbers, so
  the model cannot invent a quote.
- A schema failure gets one retry, then the document goes to `needs_human`. The model is never asked to score,
  rank, approve, send or book anything.
- The Groq fallback (`HG_GROQ_FALLBACK`) is off by default and for fictional data only.
- Candidate data stays local in production (on-prem Ollama in Tunisia). Modal is for fictional test data only.

## Input and output contract

Input: `ValidatedCV`-bound text only. Visible text comes from the sanitizer; hidden findings are never sent to the
model. With `HG_MASK_IDENTITY` on (default), towns, schools, gendered titles and emails are masked per line before
the model reads them, so line numbers stay stable.

Output, as the model returns it (before `to_extraction`):

```json
{
  "doc_language": "fr",
  "skills":      [{"esco_id": "python", "line": 7}],
  "experiences": [{"start": "2020-01", "end": null, "skills": ["python"], "line": 5}],
  "degrees":     [{"level": "licence", "year": 2018, "line": 9}],
  "languages":   [{"iso": "fr", "cefr": "C1"}]
}
```

`to_extraction` drops items that do not validate (unknown ESCO id, bad date, line out of range) instead of
failing the whole document; the validator then checks every skill against the visible text before scoring.

## Failure modes to design for

| Failure | What happens | Where it is handled |
|---|---|---|
| Endpoint down, 401, or cold start timeout (1 to 3 min) | `LLMUnavailable`, one retry on timeout/502/503/504, then `None` | `llm.py`, `extract_cv` returns None, candidate goes to `needs_human` |
| Output is not valid JSON or fails the schema | one retry, then `needs_human` | `extract_cv` |
| Model returns an unknown ESCO id or an unsupported skill | the item is dropped (evidence must sit in the visible text and contain an ESCO label of that skill); a skill with no dated job block is kept as `listed_only` | `to_extraction`, `validator.py` |
| Injection text in the CV | the model may still be moved by it; the sanitizer, detector, validator and the typed output limit the effect. Flags are a signal for HR and never change a score | measured in [evaluation.md](evaluation.md) |
| Heavy tail latency | a CV can take over a minute on a cold container (smoke test: median 12 s, p90 74 s) | set `HG_LLM_TIMEOUT` (300 s for evaluation runs) |

Limits: 8192-token request context; long CVs are cut to `MAX_LINES` lines (`extractor.py`).

## Measured on this setup (1 Nov 2026)

Full tables and confidence intervals: [evaluation.md](evaluation.md); raw results `eval/results/summary.json`.

| Measure | Result |
|---|---|
| Extraction, 200 CVs | skill precision 0.999, recall 0.894, F1 0.944; French 0.966, English 0.967, **Arabic 0.800** (recall 0.667); years MAE 0.23; degree correct 185/200; 2/200 sent to a human |
| Failed model calls | 4 in the extraction section of 407 calls; 0 in attacks, twins and emails |
| Attacks through the model | 3/40 moved (naive screener: 13/40), paired p = 0.0063 |
| Supplementary attacks (visible instructions, visible stuffing, bidi) | 7/14 moved: the sanitizer cannot remove visible text |
| Emails | right lane 100/100, urgency 80/100, language 98/100 |
| Twins with identity masking | 17/89 changed (26/90 before masking); language swaps 13/20 |

Failure patterns to expect: Arabic CVs lose about a third of their skills, urgency labels are the weakest email field,
and visible instructions or fake skills in the body of a CV can still move the extraction.

## How to rerun the evaluation

```powershell
cd hireguard
$py = "backend\.venv\Scripts\python.exe"
# put HG_OLLAMA_HOSTS, HG_OLLAMA_MODAL_KEY, HG_OLLAMA_MODAL_SECRET in hireguard\.env.modal (git-ignored)
& $py eval\gen_cvs.py --count 200 --pdf
& $py eval\gen_attacks.py
& $py eval\gen_twins.py
& $py eval\harness.py --extraction llm
& $py eval\fairness.py --extraction llm
& $py eval\load_test.py --n 300 --extraction llm
modal app stop hireguard-ollama      # stop paying when finished
```

Run `harness.py` with the environment loaded; the result file records the model name and extraction mode.
