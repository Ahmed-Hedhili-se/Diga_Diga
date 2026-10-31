# Evaluation (P2)

Every number is reported as **k/n with a Clopper-Pearson 95% interval**, e.g. `2/40 (5.0%, 95% CI 0.6–16.9%)`. A rate without n is never shown. No result below has been measured yet: all are **TBD** until `eval/harness.py` runs on the real pipeline.

## How to run

```powershell
cd hireguard
$py = "backend\.venv\Scripts\python.exe"
& $py eval\gen_cvs.py --count 200 --pdf   # 200 synthetic CVs + ground truth (data/cv_ground_truth/)
& $py eval\gen_attacks.py                 # 40 in-house attacks + payload-free twins (eval/corpus/attacks/)
& $py eval\gen_twins.py                   # 10 base CVs x up to 10 counterfactual variants (eval/corpus/twins/)
& $py eval\harness.py                     # -> eval/results/summary.json, served at GET /api/eval/summary
```

The harness calls `app.pipeline.service.analyze_pdf(pdf_bytes, candidate_id) -> (SanitizeResult, ValidatedCV)` (P1). It scores against the frozen rubric files in `data/rubrics/`, not HR's DB edits, so runs are reproducible.

## What is measured

| Metric | Definition | Data | Result |
|---|---|---|---|
| Attack success | Any validated field, the score, or the rank differs from the payload-free twin | 40 in-house attacks (9 channels, EN/FR/AR/Derja/Arabizi) | TBD |
| Attack success, outsider | Same definition | 30 sealed attacks written outside the team, opened once at the final run | TBD |
| Baseline attack success | Same attacks against a WithSecure/Reversec-style screener (raw CV in prompt, free-text verdict) on the same model | `eval/baselines.py` (stub) | TBD |
| ResumeShield | Detection on 72 injected docs, false alarms on 32 clean docs | 104 docs | TBD |
| Hidden-text detection | Doc-level precision/recall: the sanitizer reports the expected channel on the attacked file; any finding on a twin = false positive | 40 attacks + 40 twins | TBD |
| Instruction flagged | Share of instruction payloads that raise an `injection_flag` (a signal only, never a score input) | Instruction subset | TBD |
| Extraction F1 | ESCO skill set vs ground truth; MAE of years computed from dates | 200 CVs (≈52% FR, 32% EN, 16% AR) | TBD |
| Counterfactual invariance | Score changes when only town (La Marsa/Sfax/Kasserine/Tataouine), school (SUP'COM/ISET/private), a 12-month gap, CV language, or ingénieur/ingénieure changes | 10 groups, 90 variants | TBD (must be 0/90) |
| Ranking sanity | Kendall tau and Cohen kappa vs 2 outside annotators | TBD set | TBD |
| Email routing | Accuracy, incl. 15 spoofed (with P3) | 100 emails | TBD |

## Fairness by construction

`score()` takes only `ValidatedCV` and `Rubric`. `ValidatedCV` has no name, town, school, gender or email field, and `tests/test_scoring.py::test_scorer_cannot_see_identity_fields` enforces that. The twin eval checks the other half: that extraction doesn't leak these attributes into the fields that are scored.

## Known limits

- The CVs are synthetic, generated from templates. Real CVs are messier, so extraction F1 here is an upper bound.
- Arabic PDFs extract as presentation forms (U+FExx). The sanitizer must NFKC-normalize before matching.
- The attack corpus is written by the team (in-house). The sealed outsider set exists to measure what we didn't think of.
