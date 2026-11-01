"""HireGuard and HR Nexus stay separate: neither module imports the other or reads its data.

HireGuard holds identifiable candidate and employee records; HR Nexus works on team-level aggregates (k >= 5).
Joining them would need an approved purpose and a documented boundary, so any coupling must fail this test first.
"""
import re

from app.config import ROOT

REPO = ROOT.parent
HIREGUARD_APP = ROOT / "backend" / "app"
HRNEXUS_DIRS = [REPO / d for d in ("src", "experiments", "scripts") if (REPO / d).is_dir()]

HRNEXUS_MARKERS = re.compile(r"\bhrnexus\b|\bhr_nexus\b|data[/\\]raw", re.I)
HIREGUARD_MARKERS = re.compile(r"\bfrom app\b|\bimport app\b|hireguard\.db|\bauth_users\b|\bpipeline_docs\b|"
                               r"\bscore_results\b|\bapproval_items\b|\bemployee_questions\b|\bworkflow_employees\b")


def test_hireguard_never_touches_hr_nexus():
    hits = [p.name for p in HIREGUARD_APP.rglob("*.py") if HRNEXUS_MARKERS.search(p.read_text(encoding="utf-8"))]
    assert not hits, f"HireGuard code references HR Nexus: {hits}"


def test_hr_nexus_never_reads_hireguard_records():
    hits = [str(p.relative_to(REPO)) for d in HRNEXUS_DIRS for p in d.rglob("*.py")
            if HIREGUARD_MARKERS.search(p.read_text(encoding="utf-8", errors="ignore"))]
    assert not hits, f"HR Nexus code references HireGuard records: {hits}"
