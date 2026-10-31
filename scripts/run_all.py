"""Run every experiment in order and stop at the first failure.

    python scripts/download_data.py
    python scripts/run_all.py
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = [
    "e1_workload_patterns.py",
    "e2_org_graph.py",
    "e3_skills_capability.py",
    "e4_wellbeing_relationships.py",
    "e5_early_risk.py",
    "e6_scenarios.py",
    "e7_graph_schema_demo.py",
]

for name in EXPERIMENTS:
    t0 = time.time()
    print(f"== {name}", flush=True)
    subprocess.run([sys.executable, str(ROOT / "experiments" / name)], check=True, cwd=ROOT)
    print(f"   done in {time.time() - t0:.0f}s", flush=True)
