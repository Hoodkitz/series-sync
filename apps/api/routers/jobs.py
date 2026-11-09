"""Dubbing job API endpoints."""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from uuid import UUID

router = APIRouter(prefix="/api/v1", tags=["jobs"])


class JobCreateRequest(BaseModel):
    tenant_id: UUID
    source_video_url: str
    source_language: str = "en"
    target_language: str = "de"


@router.post("/jobs")
async def create_job(req: JobCreateRequest):
    return {"job_id": str(UUID(int=1)), "status": "uploaded"}


@router.get("/jobs/{job_id}")
async def get_job(job_id: UUID):
    return {"job_id": str(job_id), "status": "uploaded", "quality_score": None}


@router.get("/jobs/{job_id}/qa-report")
async def get_qa_report(job_id: UUID):
    return {"job_id": str(job_id), "lip_sync_score": 0.0, "audio_quality_score": 0.0, "translation_accuracy_score": 0.0, "overall_pass": False, "issues": []}


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: UUID):
    return {"job_id": str(job_id), "status": "cancelled"}
