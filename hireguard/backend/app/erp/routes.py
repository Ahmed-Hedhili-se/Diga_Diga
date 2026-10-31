"""ERP endpoints. Read-only toward Odoo: writes happen only in the executor (handlers.py)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..auth.core import require_roles
from ..contracts import Role, UserOut
from ..scoring.jobs import JOBS
from . import handlers, odoo_client, sync
from .odoo_client import OdooError

handlers.install()

router = APIRouter()

RM = require_roles(Role.recruiter, Role.hr_manager)
RMA = require_roles(Role.recruiter, Role.hr_manager, Role.admin)


def _job(job_id: str) -> str:
    if job_id not in JOBS:
        raise HTTPException(404, "job not found")
    if not odoo_client.ENABLED:
        raise HTTPException(409, "Odoo connector is disabled (HG_ODOO_ENABLED=0)")
    return job_id


@router.get("/erp/status")
def erp_status(user: UserOut = Depends(RMA)):
    return odoo_client.status()


@router.get("/erp/jobs/{job_id}/applicants")
def erp_applicants(job_id: str, user: UserOut = Depends(RM)):
    try:
        return sync.list_applicants(_job(job_id))
    except OdooError as e:
        raise HTTPException(502, f"Odoo unavailable: {e}")


@router.post("/erp/jobs/{job_id}/import")
def erp_import(job_id: str, user: UserOut = Depends(RM)):
    try:
        return sync.import_applicants(_job(job_id), actor=user.id)
    except OdooError as e:
        raise HTTPException(502, f"Odoo unavailable: {e}")
