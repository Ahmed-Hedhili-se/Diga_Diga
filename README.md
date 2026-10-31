# HR Nexus: feasibility research for privacy-preserving workforce intelligence

This repository holds the experiments and the research report that test whether
an AI-assisted **HR workforce-intelligence and decision-support system** is
scientifically defensible, technically buildable and legally deployable.

The full write-up is in **[docs/REPORT.md](docs/REPORT.md)**.

## What is here

| Path | Contents |
|---|---|
| `scripts/download_data.py` | Downloads every public dataset (stdlib only) and records SHA-256 hashes in `data/raw/MANIFEST.json` |
| `scripts/run_all.py` | Runs all experiments in order |
| `src/hrnexus/` | Shared code: dataset loaders, graph helpers, plotting style, and the k-anonymity aggregation guard |
| `experiments/e1_workload_patterns.py` | Workload and pressure anomaly detection (SNAP email-Eu-core-temporal, UCI Absenteeism) |
| `experiments/e2_org_graph.py` | Collaboration-graph analysis: silos, brokerage, key-person dependency, stability (SNAP email-Eu-core, SocioPatterns) |
| `experiments/e3_skills_capability.py` | Text-to-skill-profile mapping and team capability coverage (O*NET 31.0, Anthropic Economic Index) |
| `experiments/e4_wellbeing_relationships.py` | Work conditions vs. self-reported stress, exhaustion and satisfaction (GSS Quality of Worklife 2002-2022) |
| `experiments/e5_early_risk.py` | Team-level forecasting, coordination-channel collapse prediction and survival analysis |
| `experiments/e6_scenarios.py` | Multi-objective what-if simulation (synthetic, clearly labelled) |
| `experiments/e7_graph_schema_demo.py` | Organizational graph schema, example instance and explainable team profiles (synthetic) |
| `results/<experiment>/` | `metrics.json`, CSV tables and `figures/*.png` produced by each experiment |

## Reproduce

Python 3.11 on Windows, macOS or Linux.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt        # torch CPU wheel: see the comment in requirements.txt
python scripts/download_data.py        # ~180 MB, all public and openly licensed
python scripts/run_all.py              # ~8 minutes on a laptop CPU
```

Every random step uses a fixed seed (`hrnexus.common.SEED`), so the numbers in
the report come back unchanged. The first run of Experiment 3 downloads the
`all-MiniLM-L6-v2` sentence-embedding model (~90 MB) from Hugging Face and
caches task embeddings in `data/cache/`.

## Ground rules that the code enforces

* No message content is used anywhere. Communication data is metadata only.
* Person-level features are computed only to build team-level indicators and
  are never written to `results/` with identifiers. Team aggregates built from
  fewer than 5 people are suppressed (`k_anonymous_aggregate`).
* Synthetic data is used only where no real data exists (Experiments 3B, 6, 7),
  and every such output is labelled synthetic.
