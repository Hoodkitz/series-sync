"""Pipeline API endpoints for Series Sync."""
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import select
from uuid import UUID
from datetime import datetime

from apps.api.security.auth import get_current_active_user
from apps.api.security.permissions import check_permission
from apps.core.permissions import Permission
from apps.db.models import User

from apps.api.schemas.pipeline import (
    JobCreate, JobResponse, JobListResponse, QAReportResponse,
    StageAdvance, StageResponse
)
from apps.db.session import get_session, engine
from apps.db.models import SyncJob as SyncJobModel, VoiceProfile as VoiceProfileModel, Tenant as TenantModel
from apps.services.dubbing_pipeline import DubbingPipeline
from apps.services.fakes.asr import FakeASRService
from apps.services.fakes.translation import FakeTranslationService
from apps.services.fakes.tts import FakeTTSService
from apps.services.fakes.lipsync import FakeLipSyncService
from apps.services.fakes.qa import FakeQAService

router = APIRouter(prefix="/jobs", tags=["pipeline"])

def get_pipeline():
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return DubbingPipeline(
        asr=FakeASRService(),
        translator=FakeTranslationService(),
        tts=FakeTTSService(),
        lipsync=FakeLipSyncService(),
        qa=FakeQAService(),
        session_factory=session_factory
    )


@router.post("", response_model=JobResponse)
async def create_job(req: JobCreate, background_tasks: BackgroundTasks, current_user: User = Depends(check_permission(Permission.CREATE_JOB)), session: AsyncSession = Depends(get_session)):
    # The tenant always comes from the authenticated user, never from the request body.
    if req.tenant_id is not None and req.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    if req.idempotency_key:
        existing = (await session.execute(select(SyncJobModel).where(
            SyncJobModel.tenant_id == current_user.tenant_id,
            SyncJobModel.idempotency_key == req.idempotency_key))).scalars().first()
        if existing:
            return existing
    job = SyncJobModel(
        tenant_id=current_user.tenant_id,
        idempotency_key=req.idempotency_key,
        source_video_url=req.source_video_url,
        source_language=req.source_language,
        target_language=req.target_language,
        rights=req.rights,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    pipeline = get_pipeline()
    background_tasks.add_task(pipeline.run_pipeline, job.id, req.voice_profile_id, current_user.tenant_id)

    return job


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, current_user: User = Depends(check_permission(Permission.READ_JOB)), session: AsyncSession = Depends(get_session)):
    stmt = select(SyncJobModel).where(SyncJobModel.id == job_id, SyncJobModel.tenant_id == current_user.tenant_id)
    result = await session.execute(stmt)
    job = result.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/tenant/{tenant_id}")
async def list_jobs(tenant_id: UUID, current_user: User = Depends(check_permission(Permission.READ_JOB)), session: AsyncSession = Depends(get_session)):
    if tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    stmt = select(SyncJobModel).where(SyncJobModel.tenant_id == tenant_id)
    result = await session.execute(stmt)
    return JobListResponse(jobs=[j async for j in result.scalars])


@router.post("/{job_id}/qa")
async def run_qa(job_id: str, current_user: User = Depends(check_permission(Permission.UPDATE_JOB)), session: AsyncSession = Depends(get_session)):
    pipeline = get_pipeline()
    job = await session.get(SyncJobModel, job_id)
    if job is not None and job.tenant_id != current_user.tenant_id:
        job = None
    if not job or not job.final_video or not job.translation:
        raise HTTPException(status_code=404, detail="Job not ready for QA")

    qa = await pipeline.qa.validate(job.final_video, job.translation)
    job.qa_report = qa
    job.quality_score = (qa["lip_sync_score"] + qa["audio_quality_score"] + qa["translation_accuracy_score"]) / 3
    await session.commit()
    return qa


@router.get("/{job_id}/qa-report")
async def get_qa_report(job_id: str, current_user: User = Depends(check_permission(Permission.READ_JOB)), session: AsyncSession = Depends(get_session)):
    stmt = select(SyncJobModel).where(SyncJobModel.id == job_id, SyncJobModel.tenant_id == current_user.tenant_id)
    result = await session.execute(stmt)
    job = result.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.qa_report:
        raise HTTPException(status_code=404, detail="No QA report available")
    return job.qa_report


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str, current_user: User = Depends(check_permission(Permission.CANCEL_JOB)), session: AsyncSession = Depends(get_session)):
    """Cancel a running job (tenant-scoped)."""
    job = (await session.execute(select(SyncJobModel).where(
        SyncJobModel.id == job_id, SyncJobModel.tenant_id == current_user.tenant_id))).scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in ("completed", "failed"):
        job.status = "failed"
        job.errors = (job.errors or []) + ["cancelled by user"]
        await session.commit()
    return {"status": "cancelled", "job_id": job_id}
