"""Pipeline API endpoints for Series Sync."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime
from apps.api.schemas.pipeline import (
    JobCreate, JobResponse, JobListResponse, QAReportResponse,
    StageAdvance, StageResponse
)
from apps.db.session import get_session
from apps.db.models import SyncJob as SyncJobModel, VoiceProfile as VoiceProfileModel, Tenant as TenantModel
from apps.services.dubbing_pipeline import DubbingPipeline, get_pipeline

router = APIRouter(prefix="/jobs", tags=["pipeline"])


@router.post("", response_model=JobResponse)
async def create_job(req: JobCreate, session: AsyncSession = Depends(get_session)):
    stmt = select(TenantModel).where(TenantModel.id == req.tenant_id)
    tenant = (await session.execute(stmt)).scalars().first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    pipeline = await get_pipeline()
    job = await pipeline.create_job(str(req.tenant_id), req.source_video_url, req.source_language, req.target_language)
    return job


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, session: AsyncSession = Depends(get_session)):
    stmt = select(SyncJobModel).where(SyncJobModel.id == job_id)
    result = await session.execute(stmt)
    job = result.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/tenant/{tenant_id}")
async def list_jobs(tenant_id: UUID, session: AsyncSession = Depends(get_session)):
    stmt = select(SyncJobModel).where(SyncJobModel.tenant_id == tenant_id)
    result = await session.execute(stmt)
    return JobListResponse(jobs=[j async for j in result.scalars])


@router.post("/{job_id}/advance")
async def advance_stage(job_id: str, req: StageAdvance, session: AsyncSession = Depends(get_session)):
    pipeline = await get_pipeline()
    job = await pipeline.advance_stage(job_id, req.stage)
    return job


@router.post("/{job_id}/qa")
async def run_qa(job_id: str, session: AsyncSession = Depends(get_session)):
    pipeline = await get_pipeline()
    qa = await pipeline.run_qa(job_id)
    return QAReportResponse(
        job_id=qa.job_id,
        lip_sync_score=qa.lip_sync_score,
        audio_quality_score=qa.audio_quality_score,
        translation_accuracy_score=qa.translation_accuracy_score,
        overall_pass=qa.overall_pass,
        issues=qa.issues,
        notes=qa.notes,
    )


@router.post("/{job_id}/complete")
async def complete_job(job_id: str, output_url: str, session: AsyncSession = Depends(get_session)):
    pipeline = await get_pipeline()
    job = await pipeline.complete_job(job_id, output_url)
    return job


@router.get("/{job_id}/qa-report")
async def get_qa_report(job_id: str, session: AsyncSession = Depends(get_session)):
    stmt = select(SyncJobModel).where(SyncJobModel.id == job_id)
    result = await session.execute(stmt)
    job = result.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.qa_report:
        raise HTTPException(status_code=404, detail="No QA report available")
    return job.qa_report


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str, session: AsyncSession = Depends(get_session)):
    """Cancel a running job."""
    # In production: check Celery task status and revoke
    return {"status": "cancelled", "job_id": job_id}
