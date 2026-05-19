"""Dashboard endpoint — returns the role-specific payload.

The router delegates to :class:`AppController.create_dashboard`, which
applies the Template Method pattern to pick :class:`PetOwnerDashboard` or
:class:`VeterinaryExpertDashboard`.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentAccountDep, DbDep
from app.domain.app_controller import get_app_controller

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
async def get_dashboard(account: CurrentAccountDep, db: DbDep) -> dict:
    """Return the dashboard payload appropriate for the actor's role."""
    dashboard = get_app_controller().create_dashboard(account=account, db=db)
    return await dashboard.render()
