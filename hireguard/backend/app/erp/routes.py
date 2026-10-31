"""ERP endpoints. Read-only toward Odoo: writes happen only in the executor (handlers.py)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..auth.core import require_permission
from ..auth.permissions import Permission
from ..contracts import UserOut
from ..scoring.jobs import JOBS
from . import handlers, odoo_client, sync
from .odoo_client import OdooError

handlers.install()

router = APIRouter()

STATUS = require_permission(Permission.erp_status)
IMPORT = require_permission(Permission.erp_import)


def _job(job_id: str) -> str:
    if job_id not in JOBS:
        raise HTTPException(404, "job not found")
    if not odoo_client.ENABLED:
        raise HTTPException(409, "Odoo connector is disabled (HG_ODOO_ENABLED=0)")
    return job_id


@router.get("/erp/status")
def erp_status(user: UserOut = Depends(STATUS)):
    return odoo_client.status()


@router.get("/erp/jobs/{job_id}/applicants")
def erp_applicants(job_id: str, user: UserOut = Depends(IMPORT)):
    try:
        return sync.list_applicants(_job(job_id))
    except OdooError as e:
        raise HTTPException(502, f"Odoo unavailable: {e}")


@router.post("/erp/jobs/{job_id}/import")
def erp_import(job_id: str, user: UserOut = Depends(IMPORT)):
    try:
        return sync.import_applicants(_job(job_id), actor=user.id)
    except OdooError as e:
        raise HTTPException(502, f"Odoo unavailable: {e}")
