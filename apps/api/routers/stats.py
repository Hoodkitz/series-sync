"""Usage statistics for the caller's tenant."""
from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.schemas.pipeline import StatsResponse
from apps.api.security.permissions import check_permission
from apps.core.permissions import Permission
from apps.db.models import SyncJob, User
from apps.db.session import get_session

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("", response_model=StatsResponse)
async def tenant_stats(user: User = Depends(check_permission(Permission.READ_JOB)),
                       session: AsyncSession = Depends(get_session)):
    def count(cond):
        return func.coalesce(func.sum(case((cond, 1), else_=0)), 0)

    row = (await session.execute(select(
        func.count(SyncJob.id),
        count(SyncJob.status == "completed"),
        count(SyncJob.status == "hitl_review"),
        count(SyncJob.status == "failed"),
        func.coalesce(func.sum(case((SyncJob.status == "completed", SyncJob.duration_seconds), else_=0.0)), 0.0),
    ).where(SyncJob.tenant_id == user.tenant_id))).one()
    total, completed, review, failed, seconds = row
    return StatsResponse(total_jobs=total, completed_jobs=completed, in_review=review, failed=failed,
                         processing=total - completed - review - failed, minutes_dubbed=round(seconds / 60, 1))
