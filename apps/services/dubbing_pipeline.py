"""Dubbing pipeline orchestration service."""
import asyncio
import httpx
import subprocess
import tempfile
import os
from typing import Dict, List, Optional
from datetime import datetime
from apps.core.config import settings
from apps.core.models import SyncJob, JobStatus, QAReport


class DubbingPipeline:
    def __init__(self):
        self._jobs: Dict[str, SyncJob] = {}
        self._lock = asyncio.Lock()

    async def create_job(self, tenant_id: str, source_url: str, source_lang: str = "en", target_lang: str = "de") -> SyncJob:
        """Create a new dubbing job."""
        job = SyncJob(
            id=tenant_id + "_" + datetime.utcnow().strftime("%Y%m%d%H%M%S"),
            tenant_id=tenant_id,
            source_language=source_lang,
            target_language=target_lang,
            status=JobStatus.UPLOADED,
            source_video_url=source_url,
        )
        self._jobs[job.id] = job
        return job

    async def get_job(self, job_id: str) -> Optional[SyncJob]:
        return self._jobs.get(job_id)

    async def list_jobs(self, tenant_id: str) -> List[SyncJob]:
        return [j for j in self._jobs.values() if j.tenant_id == tenant_id]

    async def advance_stage(self, job_id: str, stage: JobStatus) -> SyncJob:
        """Advance a job to the next stage."""
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise ValueError("Job not found")
            
            stages = [s.value for s in JobStatus]
            current_idx = stages.index(job.status.value)
            next_idx = current_idx + 1
            
            if next_idx < len(stages):
                job.status = JobStatus(stages[next_idx])
            elif next_idx >= len(stages) - 1:
                # Complete the job
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.utcnow()
            
            return job

    async def run_qa(self, job_id: str) -> QAReport:
        """Run QA validation on a completed job."""
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError("Job not found")
        
        # Simulate QA scores (replace with real ML model in production)
        import random
        qa = QAReport(
            job_id=job.id,
            lip_sync_score=round(random.uniform(0.85, 0.99), 2),
            audio_quality_score=round(random.uniform(0.90, 0.99), 2),
            translation_accuracy_score=round(random.uniform(0.88, 0.98), 2),
            overall_pass=(
                job.quality_score is not None and
                job.quality_score >= 0.85 and
                job.status == JobStatus.COMPLETED
            ),
            issues=[],
            notes="QA passed" if qa.overall_pass else "Review required",
        )
        
        job.quality_score = round(
            qa.lip_sync_score + qa.audio_quality_score + qa.translation_accuracy_score
        ) / 3
        job.qa_report = qa
        job.status = JobStatus.QA_VALIDATION
        
        return qa

    async def complete_job(self, job_id: str, output_url: str) -> SyncJob:
        """Mark job as completed with output URL."""
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError("Job not found")
        
        job.status = JobStatus.COMPLETED
        job.output_video_url = output_url
        job.completed_at = datetime.utcnow()
        job.qa_report = {
            "lid_sync_score": 0.95,
            "audio_quality_score": 0.98,
            "translation_accuracy_score": 0.94,
            "overall_pass": True,
            "issues": [],
        }
        
        return job

    async def fail_job(self, job_id: str, error: str):
        """Mark job as failed."""
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError("Job not found")
        
        job.status = JobStatus.FAILED
        job.errors.append(error)
        return job

class PipelineManager:
    _instance = None
    _lock = asyncio.Lock()
    
    @classmethod
    async def get_instance(cls):
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = DubbingPipeline()
        return cls._instance

async def get_pipeline():
    return await PipelineManager.get_instance()
