"""POST /api/agent/plan: build today's plan. Creates no approval item and changes no data except one audit entry."""
from fastapi import APIRouter, Depends

from ..auth.core import require_permission
from ..auth.permissions import Permission
from ..contracts import UserOut
from . import planner

router = APIRouter()
PLAN = require_permission(Permission.agent_plan)


@router.post("/agent/plan")
def agent_plan(user: UserOut = Depends(PLAN)):
    return planner.run(user)
