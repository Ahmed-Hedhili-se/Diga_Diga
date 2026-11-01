# Hedhili - AI model training, setup, and testing

## Mission

Own every task that requires an AI model or GPU: model selection, local setup,
training or tuning only when justified, inference testing, and reproducible
evaluation. No model result is a release claim until it has been measured on the
actual configured model and reviewed with the team.

## Status (1 Nov, evening)

Done: Answer Desk, P3 follow-ups and hardening, the pentest, the Modal app, identity masking, the naive-screener
baseline, the masked model run, the detector and attack-generator fixes. Setup record and hand-off to Rayen:
[hireguard/docs/model_config.md](../hireguard/docs/model_config.md).

- [x] **P0** Masked model evaluation on Modal (Qwen3-8B `Q4_K_M`, L4 GPU), results in `eval/results/summary.json`:
      attacks **3/40** vs **13/40** for the naive screener (McNemar p = 0.0063); emails 100/100; twins **17/89**
      (26/90 before masking; town, school and gender 0, CV language 13/20, gap 4/9); supplementary attacks 7/14.
- [x] **P0** Extraction on **200 CVs**: skill F1 0.944 (precision 0.999, recall 0.894); Arabic F1 0.80; years MAE 0.23;
      degree correct 92.5%; 4 failed model calls.
- [x] **P0** Where the model ran is recorded in every result file (`runtime`: Modal cloud, NVIDIA L4, digest, settings).
- [x] **P1** Attack generator fix (`keep_proportion=False`): detection **40/40**, 0/40 on clean twins.
- [x] **P1** Instructions flagged: **28/28** on `attacks`, 11/11 on `attacks_extra`, 0 false alarms on 200 clean CVs.
- [x] Fixed `eval/fairness.py`, which imported a function that no longer existed in `harness.py`.

Still open (for the team, not blocked on a GPU):

- [ ] **Visible attacks**: 7/14 supplementary attacks moved a field or score (visible instructions 3/8, bidi 2/4,
      visible stuffing 2/2). The detector flags instructions but not stuffing. Decide with Ahmed how the pitch states this;
      Rayen's `listed_only` weighting (<= 0.3) should reduce the effect of stuffing.
- [ ] **Arabic extraction (diagnosed 1 Nov, fix not yet measured).** Arabic CVs lose 55 of 165 skills (recall 0.67). In the
      CVs checked, the skills written in Arabic (`إدارة شؤون الموظفين`, `التوظيف`) are never proposed by the model, while Latin-script
      ones are. Cause: `extractor._esco_list()` shows only the English label (`hr-administration: Personnel administration`) although
      `data/esco_subset.json` already holds `fr` and `ar` labels. Fix to try: list the Arabic and French labels next to each id,
      then re-run extraction on the 33 Arabic CVs, then on all 200, and the twins (language swaps move the score 13/20).
      This changes the prompt, so re-measure everything before quoting it.
- [ ] Outsider attack set (30 sealed attacks written outside the team), opened once at the final run.
- [ ] Re-run `backend` tests on a real venv: 7 route-table tests fail on the measuring machine (5 also fail on a clean `HEAD`).
- [ ] Stop the Modal app when finished: `modal app stop hireguard-ollama`.


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
