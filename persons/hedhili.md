# Hedhili - AI model training, setup, and testing

## Mission

Own every task that requires an AI model or GPU: model selection, local setup,
training or tuning only when justified, inference testing, and reproducible
evaluation. No model result is a release claim until it has been measured on the
actual configured model and reviewed with the team.

## Start here (31 Oct hand-off)

Everything published so far is **oracle mode** (code path only). Your numbers
replace every "TBD (LLM)" on the metrics slide. On the GPU laptop, from `hireguard/`:

```powershell
ollama pull qwen3:8b
$py = "backend\.venv\Scripts\python.exe"
& $py eval\harness.py --extraction llm      # attacks, twins, extraction F1 through the model
& $py eval\fairness.py --extraction llm     # group audit on model extractions
& $py eval\load_test.py --n 300 --extraction llm
```

- [ ] R1: run the three commands; commit the result JSONs; report per language and per attack.
- [ ] Baseline: the same 40 attacks against a naive "LLM ranks the CV" prompt; paired
      McNemar (p = 2 x 0.5^b; significant for b >= 6).
- [ ] R2: close the detector misses (English "Evaluator note" 4/4, Derja 3/3, Arabic 3/4)
      in `backend/app/pipeline/detector.py` with tests; re-run the harness.
- [ ] Record model name, digest, quantization, context size and runtime settings.

## Work to execute

### Model setup and interface

- [ ] Inventory available GPUs, memory, runtime, and model-serving options.
- [ ] Select the smallest model that meets the typed extraction requirements;
      document trade-offs and operational constraints.
- [ ] Establish a reproducible local inference setup and record model name,
      version/hash, runtime settings, and test environment.
- [ ] Confirm inference has no tools, external actions, or cross-document
      memory. Keep candidate data local unless the team explicitly approves a
      documented alternative.
- [ ] Agree with Rayen on the typed model input/output contract and failure
      behavior before changing extraction schemas.

### Testing and evaluation

- [ ] Evaluate extraction quality against the available ground truth across
      French, English, Arabic, and relevant Tunisian language variants.
- [ ] Measure schema-valid output, skill extraction precision/recall or F1,
      date/experience errors, refusals, latency, and failure rates.
- [ ] Run prompt-injection and hostile-document tests, including hidden text,
      visible instructions, homoglyphs, zero-width/bidi characters, and
      multilingual attacks.
- [ ] Verify attacks cannot cause extra fields, fabricated evidence, score
      changes unsupported by validated data, or any action.
- [ ] Compare against a simple baseline where feasible. State exactly what the
      baseline is; do not describe an unimplemented stub as a measured result.
- [ ] Separate oracle-mode code-path tests from tests that actually invoke the
      model. Never report oracle results as model robustness.
- [ ] Repeat tests after model, prompt, sanitizer, or schema changes and save
      reproducible result files.

### Hardening and handoff

- [ ] Provide Rayen with the model's schema, tested examples, failure modes,
      limits, and inference configuration.
- [ ] Require deterministic validation of all model output before scoring.
- [ ] Report any language-specific or attack-specific failures; do not hide them
      behind an aggregate metric.
- [ ] Recommend a model change or fine-tuning only when measured errors justify
      it and there is suitable, permissioned training data.
- [ ] Review model upgrades for regressions, privacy, licensing, resource use,
      and attack behavior.

## Security responsibility

Treat every CV and email as adversarial input. The model may extract typed
proposals only; it must never decide who is hired, approve an item, send an
email, book an interview, or access tools. Coordinate adversarial tests with
Ahmed and Rayen, and provide evidence for every claimed safeguard.

## Deliverables

- Reproducible GPU/model setup instructions.
- Model and inference configuration record.
- Evaluation dataset/run command and result summary with sample counts and
  limitations.
- Adversarial test results with missed cases and remediation status.
- Typed interface examples and a clear handoff to Rayen.

## Definition of done

The team can rerun the model evaluation on the declared hardware, inspect
per-language and attack-specific results, and verify that invalid or manipulated
model output is rejected before it can affect a score or workflow action.
