"""Stats endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from apps.api.schemas.pipeline import StatsResponse
from apps.db.session import get_session
from apps.db.models import SyncJob as SyncJobModel

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/job-status/{tenant_id}")
async def get_job_status(tenant_id: UUID, session: AsyncSession = Depends(get_session)):
    stmt = select(SyncJobModel).where(SyncJobModel.tenant_id == tenant_id)
    result = await session.execute(stmt)
    jobs = result.scalars().all()
    
    completed = sum(1 for j in jobs if j.status == "completed")
    active = sum(1 for j in jobs if j.status in ["completed", "failed"])
    total = len(jobs)
    
    return StatsResponse(
        tenant_id=str(tenant_id),
        completed_jobs=completed,
        total_jobs=total,
        jobs=[
            {"id": str(j.id), "status": j.status, "quality_score": j.quality_score}
            for j in jobs
        ],
    )
