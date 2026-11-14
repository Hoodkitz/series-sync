"""Background worker service to discover and resume interrupted or quota-paused jobs."""
from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from sqlalchemy import select

from apps.core.models import JobStatus
from apps.db.models import SyncJob, Tenant
from apps.db.session import set_tenant_context
from apps.services.dubbing_pipeline import DubbingPipeline, is_running

log = logging.getLogger("seriessync.worker")


async def get_resumable_jobs(
    session_factory,
    tenant_id: UUID | None = None,
    limit: int = 10,
) -> list[tuple[UUID, UUID, UUID | None]]:
    """Discover jobs in TTS_GENERATION or UPLOADED state that are not actively running.
    Handles Postgres RLS per tenant context or SQLite seamlessly.
    Returns: list of (job_id, tenant_id, voice_profile_id).
    """
    candidates: list[tuple[UUID, UUID, UUID | None]] = []
    target_statuses = (JobStatus.TTS_GENERATION.value, JobStatus.UPLOADED.value)

    async with session_factory() as session:
        if tenant_id is not None:
            tenant_ids = [tenant_id]
        else:
            try:
                res = await session.execute(select(Tenant.id).where(Tenant.is_active == True))
                tenant_ids = res.scalars().all()
            except Exception:
                tenant_ids = [None]

        for tid in tenant_ids:
            if tid is not None:
                await set_tenant_context(session, tid)
            stmt = select(SyncJob.id, SyncJob.tenant_id, SyncJob.voice_profile_id).where(
                SyncJob.status.in_(target_statuses)
            )
            if tid is not None:
                stmt = stmt.where(SyncJob.tenant_id == tid)
            stmt = stmt.order_by(SyncJob.created_at.asc())
            rows = (await session.execute(stmt)).all()
            for jid, job_tid, vid in rows:
                if not is_running(jid):
                    candidates.append((jid, job_tid, vid))
                    if len(candidates) >= limit:
                        return candidates
    return candidates


async def resume_job(
    session_factory,
    job_id: UUID,
    tenant_id: UUID,
    voice_profile_id: UUID | None = None,
    pipeline: DubbingPipeline | None = None,
) -> bool:
    """Resume an individual job if not already running."""
    if is_running(job_id):
        log.info("Job %s is already running, skipping", job_id)
        return False
    pipeline = pipeline or DubbingPipeline(session_factory)
    await pipeline.run_pipeline(job_id, voice_profile_id, tenant_id)
    return True


async def resume_pending_jobs(
    session_factory,
    pipeline: DubbingPipeline | None = None,
    tenant_id: UUID | None = None,
    limit: int = 10,
) -> int:
    """Find and resume all pending/paused jobs up to limit.
    Returns the number of jobs triggered.
    """
    pipeline = pipeline or DubbingPipeline(session_factory)
    jobs = await get_resumable_jobs(session_factory, tenant_id=tenant_id, limit=limit)
    resumed = 0
    for jid, tid, vid in jobs:
        log.info("Worker resuming job %s for tenant %s", jid, tid)
        try:
            await pipeline.run_pipeline(jid, vid, tid)
            resumed += 1
        except Exception:
            log.exception("Worker encountered error while running job %s", jid)
    return resumed


async def run_worker_loop(
    session_factory,
    poll_interval: float = 30.0,
    max_iterations: int | None = None,
    pipeline: DubbingPipeline | None = None,
) -> None:
    """Run an async worker loop periodically resuming pending and quota-paused jobs."""
    iteration = 0
    log.info("Worker loop started with poll_interval=%.1fs", poll_interval)
    while max_iterations is None or iteration < max_iterations:
        try:
            resumed = await resume_pending_jobs(session_factory, pipeline=pipeline)
            if resumed > 0:
                log.info("Worker resumed %d jobs in iteration %d", resumed, iteration)
        except Exception:
            log.exception("Error in worker iteration %d", iteration)
        iteration += 1
        if max_iterations is not None and iteration >= max_iterations:
            break
        await asyncio.sleep(poll_interval)
