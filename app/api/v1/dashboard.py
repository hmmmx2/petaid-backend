from fastapi import APIRouter

from app.api.deps import CurrentUserDep, DbDep
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard import build_dashboard

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
async def get_dashboard(user: CurrentUserDep, db: DbDep) -> DashboardResponse:
    return await build_dashboard(db, user)
