"""Dashboard endpoint — returns the role-specific payload.

The router delegates to :class:`AppController.create_dashboard`, which
applies the Template Method pattern to pick :class:`PetOwnerDashboard` or
:class:`VeterinaryExpertDashboard`.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import CurrentAccountDep, DbDep, require
from app.domain.app_controller import get_app_controller
from app.domain.permissions import Permission, permissions_for

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", dependencies=[Depends(require(Permission.DASHBOARD_VIEW))])
async def get_dashboard(account: CurrentAccountDep, db: DbDep) -> dict:
    """Return the dashboard payload appropriate for the actor's role.

    Includes the actor's RBAC ``permissions`` so the SPA can gate its UI from
    the same single source of truth without an extra round-trip.
    """
    dashboard = get_app_controller().create_dashboard(account=account, db=db)
    payload = await dashboard.render()
    payload["permissions"] = [p.value for p in permissions_for(account.role)]
    return payload
