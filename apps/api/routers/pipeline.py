"""Uploads and dubbing jobs (all tenant-scoped; the tenant always comes from the token)."""
from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from apps.api.schemas.pipeline import (JobCreate, JobListResponse, JobResponse, SegmentEdit, UploadResponse)
from apps.api.security.permissions import check_permission
from apps.core.config import settings
from apps.core.models import JobStatus
from apps.core.permissions import Permission
from apps.db.models import SyncJob, User, VoiceProfile
from apps.db.session import AsyncSessionLocal, get_session
from apps.media import ffmpeg, storage
from apps.services.dubbing_pipeline import DubbingPipeline

uploads = APIRouter(prefix="/uploads", tags=["uploads"])
router = APIRouter(prefix="/jobs", tags=["jobs"])

ACTIVE = {JobStatus.UPLOADED.value, JobStatus.PREPROCESSING.value, JobStatus.TRANSCRIPTION.value,
          JobStatus.TRANSLATION.value, JobStatus.TTS_GENERATION.value, JobStatus.LIP_SYNC.value,
          JobStatus.RENDERING.value, JobStatus.QA_VALIDATION.value}


def get_pipeline() -> DubbingPipeline:
    return DubbingPipeline(AsyncSessionLocal)


# ------------------------------------------------------------------ uploads
@uploads.post("", response_model=UploadResponse, status_code=201)
async def upload_video(file: UploadFile = File(...),
                       user: User = Depends(check_permission(Permission.UPLOAD_FILE))):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in storage.ALLOWED_VIDEO_EXT:
        raise HTTPException(415, f"Unsupported file type. Allowed: {', '.join(sorted(storage.ALLOWED_VIDEO_EXT))}")
    upload_id = uuid4()
    dst = storage.uploads_dir(user.tenant_id) / f"{upload_id}{ext}"
    limit = settings.MAX_UPLOAD_MB * 1024 * 1024
    size = 0
    try:
        with open(dst, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, f"File larger than {settings.MAX_UPLOAD_MB} MB")
                out.write(chunk)
        try:
            info = await ffmpeg.media_info(dst)
        except ffmpeg.MediaError:
            raise HTTPException(422, "File is not a readable video")
        if not info["has_video"] or not info["has_audio"]:
            raise HTTPException(422, "Video must contain a picture and an audio track")
        if info["duration"] > settings.MAX_DURATION_MINUTES * 60:
            raise HTTPException(422, f"Video longer than {settings.MAX_DURATION_MINUTES} minutes")
    except BaseException:
        dst.unlink(missing_ok=True)
        raise
    return UploadResponse(upload_id=upload_id, filename=(file.filename or "")[:255], size_bytes=size,
                          duration_seconds=round(info["duration"], 2))


# ------------------------------------------------------------------ jobs
async def _job(session: AsyncSession, job_id: UUID, user: User) -> SyncJob:
    job = (await session.execute(select(SyncJob).where(SyncJob.id == job_id, SyncJob.tenant_id == user.tenant_id))
           ).scalars().first()
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(req: JobCreate, background: BackgroundTasks,
                     user: User = Depends(check_permission(Permission.CREATE_JOB)),
                     session: AsyncSession = Depends(get_session),
                     pipeline: DubbingPipeline = Depends(get_pipeline)):
    if req.idempotency_key:
        existing = (await session.execute(select(SyncJob).where(
            SyncJob.tenant_id == user.tenant_id, SyncJob.idempotency_key == req.idempotency_key))).scalars().first()
        if existing:
            return existing
    if storage.upload_path(user.tenant_id, req.upload_id) is None:
        raise HTTPException(404, "Upload not found")
    if req.voice_profile_id is not None:
        voice = (await session.execute(select(VoiceProfile).where(
            VoiceProfile.id == req.voice_profile_id, VoiceProfile.tenant_id == user.tenant_id))).scalars().first()
        if not voice:
            raise HTTPException(404, "Voice profile not found")
        if not voice.consent:
            raise HTTPException(409, "Voice profile has no documented consent")
    job = SyncJob(tenant_id=user.tenant_id, idempotency_key=req.idempotency_key,
                  source_video_url=f"{storage.UPLOAD_PREFIX}{req.upload_id}", source_language=req.source_language,
                  target_language=req.target_language, rights=req.rights, voice_profile_id=req.voice_profile_id,
                  background_volume=req.background_volume, title=req.title, status=JobStatus.UPLOADED.value,
                  errors=[])
    session.add(job)
    await session.commit()
    await session.refresh(job)
    background.add_task(pipeline.run_pipeline, job.id, req.voice_profile_id, user.tenant_id)
    return job


@router.get("", response_model=JobListResponse)
async def list_jobs(limit: int = 50, offset: int = 0, user: User = Depends(check_permission(Permission.READ_JOB)),
                    session: AsyncSession = Depends(get_session)):
    limit = max(1, min(limit, 200))
    rows = (await session.execute(select(SyncJob).where(SyncJob.tenant_id == user.tenant_id)
                                  .order_by(SyncJob.created_at.desc()).limit(limit).offset(max(0, offset)))
            ).scalars().all()
    return JobListResponse(jobs=[JobResponse.model_validate(j) for j in rows])


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: UUID, user: User = Depends(check_permission(Permission.READ_JOB)),
                  session: AsyncSession = Depends(get_session)):
    return await _job(session, job_id, user)


@router.get("/{job_id}/segments")
async def get_segments(job_id: UUID, user: User = Depends(check_permission(Permission.READ_JOB)),
                       session: AsyncSession = Depends(get_session)):
    job = await _job(session, job_id, user)
    keys = ("start", "end", "text", "translation", "tempo", "overrun", "dub_seconds", "slot")
    return {"job_id": str(job.id), "segments": [
        {"index": i, **{k: s.get(k) for k in keys}} for i, s in enumerate(job.segments or [])]}


@router.patch("/{job_id}/segments/{index}")
async def edit_segment(job_id: UUID, index: int, req: SegmentEdit,
                       user: User = Depends(check_permission(Permission.UPDATE_JOB)),
                       session: AsyncSession = Depends(get_session)):
    """Human correction of one line. The line is re-voiced and the video re-rendered on the next /render."""
    job = await _job(session, job_id, user)
    if job.status in ACTIVE:
        raise HTTPException(409, "Job is still processing")
    segments = [dict(s) for s in (job.segments or [])]
    if not 0 <= index < len(segments):
        raise HTTPException(404, "Line not found")
    seg = segments[index]
    seg["translation"] = req.translation.strip()
    for key in ("fitted", "tempo", "overrun", "dub_seconds", "slot"):
        seg.pop(key, None)
    job.segments = segments
    flag_modified(job, "segments")
    job.translation = "\n".join(s.get("translation", "") for s in segments)
    job.final_video = None
    job.qa_report = None
    job.status = JobStatus.TRANSLATION.value
    await session.commit()
    return {"index": index, "translation": seg["translation"]}


@router.post("/{job_id}/render", response_model=JobResponse)
async def render(job_id: UUID, background: BackgroundTasks,
                 user: User = Depends(check_permission(Permission.UPDATE_JOB)),
                 session: AsyncSession = Depends(get_session), pipeline: DubbingPipeline = Depends(get_pipeline)):
    """Resume a failed job or re-render after edits; finished stages are reused, nothing is paid twice."""
    job = await _job(session, job_id, user)
    if job.status in ACTIVE - {JobStatus.UPLOADED.value, JobStatus.TRANSLATION.value}:
        raise HTTPException(409, "Job is still processing")
    if job.status in (JobStatus.COMPLETED.value, JobStatus.HITL_REVIEW.value) and job.final_video:
        raise HTTPException(409, "Nothing changed since the last render")
    job.status = JobStatus.UPLOADED.value
    job.errors = [e for e in (job.errors or []) if e != "cancelled by user"]
    await session.commit()
    background.add_task(pipeline.run_pipeline, job.id, job.voice_profile_id, user.tenant_id)
    return job


@router.post("/{job_id}/approve", response_model=JobResponse)
async def approve(job_id: UUID, user: User = Depends(check_permission(Permission.UPDATE_JOB)),
                  session: AsyncSession = Depends(get_session)):
    """A human reviewer accepts a job that QA sent to review."""
    job = await _job(session, job_id, user)
    if job.status != JobStatus.HITL_REVIEW.value:
        raise HTTPException(409, "Only jobs in review can be approved")
    job.status = JobStatus.COMPLETED.value
    report = dict(job.qa_report or {})
    report["approved_by"] = str(user.id)
    job.qa_report = report
    await session.commit()
    return job


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: UUID, user: User = Depends(check_permission(Permission.CANCEL_JOB)),
                     session: AsyncSession = Depends(get_session)):
    job = await _job(session, job_id, user)
    if job.status in ACTIVE:
        job.status = JobStatus.FAILED.value
        job.errors = (job.errors or []) + ["cancelled by user"]
        await session.commit()
    return {"status": job.status, "job_id": str(job.id)}


@router.get("/{job_id}/qa-report")
async def get_qa_report(job_id: UUID, user: User = Depends(check_permission(Permission.READ_JOB)),
                        session: AsyncSession = Depends(get_session)):
    job = await _job(session, job_id, user)
    if not job.qa_report:
        raise HTTPException(404, "No QA report available")
    return job.qa_report


@router.get("/{job_id}/output")
async def download(job_id: UUID, user: User = Depends(check_permission(Permission.EXPORT)),
                   session: AsyncSession = Depends(get_session)):
    job = await _job(session, job_id, user)
    if job.status not in (JobStatus.COMPLETED.value, JobStatus.HITL_REVIEW.value):
        raise HTTPException(409, "Output not ready")
    path = storage.inside_tenant(job.tenant_id, job.final_video)
    if not path or not path.exists():
        raise HTTPException(404, "Output file missing")
    name = (job.title or f"series-sync-{job.id}").replace('"', "")[:80]
    return FileResponse(path, media_type="video/mp4", filename=f"{name}.{job.target_language}.mp4")


@router.delete("/{job_id}", status_code=204)
async def delete_job(job_id: UUID, user: User = Depends(check_permission(Permission.CANCEL_JOB)),
                     session: AsyncSession = Depends(get_session)):
    job = await _job(session, job_id, user)
    if job.status in ACTIVE - {JobStatus.UPLOADED.value}:
        raise HTTPException(409, "Cancel the job before deleting it")
    storage.delete_job_files(job.tenant_id, job.id)
    src = storage.resolve_source(job.tenant_id, job.source_video_url)
    other = (await session.execute(select(SyncJob.id).where(
        SyncJob.tenant_id == user.tenant_id, SyncJob.source_video_url == job.source_video_url,
        SyncJob.id != job.id))).first()
    if src and not other:
        os.remove(src)
    await session.delete(job)
    await session.commit()
