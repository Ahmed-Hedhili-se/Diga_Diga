"""Baselines on the same model (P2). STUB: fill in at H9-12.

TODO 1, ResumeShield benchmark (104 docs, 72 injected):
  - Download the benchmark into eval/corpus/resumeshield/ (keep its labels file next to it).
  - For each doc: run app.pipeline.service.analyze_pdf and record (a) whether the injection moved any
    field or score versus its clean version when one exists, (b) whether a hidden finding or injection flag was raised.
  - Report with stats.rate(k, n): detection on the 72 injected docs and false alarms on the 32 clean ones.

TODO 2, WithSecure/Reversec vulnerable CV screener baseline:
  - Re-create its design: one prompt containing the job description + raw CV text, where the model
    returns a free-text verdict and a score. Run it on the SAME model (config.OLLAMA_MODEL) over
    eval/corpus/attacks/ (attacked + twin).
  - Attack success = the score or the verdict differs from the twin. This is the "before" number for the
    metrics slide; HireGuard's harness.py attack_success is the "after".

Write eval/results/baseline.json = {"resumeshield": {...}, "vulnerable_screener": {"attack_success": rate(...)}}
harness.py embeds it into summary.json.
"""

if __name__ == "__main__":
    raise SystemExit("baselines.py is a stub; see the TODOs in its docstring")
