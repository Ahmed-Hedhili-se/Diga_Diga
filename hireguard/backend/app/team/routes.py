"""HR Nexus (Team module) endpoints. HR managers and admins only; every output is team- or stage-level."""
import json

from fastapi import APIRouter, Depends, Query

from ..config import ROOT
from ..contracts import Role, UserOut
from ..auth.core import require_roles
from ..scoring.team_gaps import coverage, load_teams
from . import knowledge_gaps, process_metrics

router = APIRouter()

MA = require_roles(Role.hr_manager, Role.admin)
PROCESS_SIM = ROOT / "eval" / "results" / "process_sim.json"


@router.get("/team/skills")
def team_skills(user: UserOut = Depends(MA)):
    """Declared skills per team: holder counts only (gap / single holder / covered), never who holds what."""
    return [{"job_id": job_id, "team": t["name"], "team_size": len(t["members"]), "coverage": coverage(t)}
            for job_id, t in load_teams().items()]


@router.get("/team/process")
def team_process(source: str = Query("live", pattern="^(live|simulation)$"), user: UserOut = Depends(MA)):
    """Stage durations from the audit log, or the labelled simulation (eval/process_sim.py)."""
    if source == "simulation":
        if not PROCESS_SIM.exists():
            return {"source": "simulation", "status": "not_run"}
        return json.loads(PROCESS_SIM.read_text(encoding="utf-8"))
    return {"source": "live", **process_metrics.metrics(process_metrics.events_from_db())}


@router.get("/team/knowledge-gaps")
def team_knowledge_gaps(weeks: int = Query(8, ge=1, le=52), user: UserOut = Depends(MA)):
    return knowledge_gaps.radar(weeks=weeks)
