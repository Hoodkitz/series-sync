from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from uuid import UUID

from apps.db.session import get_session
from apps.db.models import SyncJob, User
from apps.api.security.auth import get_current_active_user

router = APIRouter(prefix="/stats", tags=["stats"])

@router.get("/{tenant_id}")
async def get_tenant_stats(tenant_id: UUID, current_user: User = Depends(get_current_active_user), session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(func.count(SyncJob.id)).where(SyncJob.tenant_id == tenant_id)
    )
    total_jobs = result.scalar() or 0
    
    result = await session.execute(
        select(func.count(SyncJob.id)).where(SyncJob.tenant_id == tenant_id, SyncJob.status == "completed")
    )
    completed_jobs = result.scalar() or 0

    return {
        "tenant_id": str(tenant_id),
        "total_jobs": total_jobs,
        "completed_jobs": completed_jobs,
        "jobs": []
    }
