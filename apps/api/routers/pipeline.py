"""Pipeline API endpoints."""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from uuid import UUID

router = APIRouter(prefix="/api/v1", tags=["pipeline"])
_pipeline = None


def get_pipeline():
    global _pipeline
    if _pipeline is None:
        from packages.pipeline.dubbing import DubbingPipeline
        _pipeline = DubbingPipeline()
    return _pipeline


class JobCreate(BaseModel):
    tenant_id: UUID
    source_video_url: str
    source_language: str = "en"
    target_language: str = "de"


@router.post("/jobs")
async def create_job(req: JobCreate):
    pipeline = get_pipeline()
    job = pipeline.create_job(str(req.tenant_id), req.source_video_url, req.source_language, req.target_language)
    return job


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    pipeline = get_pipeline()
    job = pipeline.get_job(job_id)
    if not job:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/jobs/{job_id}/advance")
async def advance_job(job_id: str):
    pipeline = get_pipeline()
    return pipeline.advance_stage(job_id)


@router.post("/jobs/{job_id}/qa")
async def run_qa(job_id: str):
    pipeline = get_pipeline()
    return pipeline.run_qa(job_id)


@router.post("/jobs/{job_id}/complete")
async def complete_job(job_id: str):
    pipeline = get_pipeline()
    return pipeline.complete(job_id)


@router.get("/jobs/tenant/{tenant_id}")
async def list_jobs(tenant_id: UUID):
    pipeline = get_pipeline()
    return {"jobs": pipeline.list_jobs(str(tenant_id))}
