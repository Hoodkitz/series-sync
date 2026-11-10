"""Dubbing pipeline orchestration."""
from enum import Enum
from typing import Dict, List, Optional
from datetime import datetime
from uuid import UUID, uuid4


class PipelineStage(str, Enum):
    UPLOADED = "uploaded"
    PREPROCESSING = "preprocessing"
    AUDIO_SEPARATION = "audio_separation"
    DIARIZATION = "diarization"
    TRANSCRIPTION = "transcription"
    TRANSLATION = "translation"
    TTS_GENERATION = "tts_generation"
    LIP_SYNC = "lip_sync"
    QA_VALIDATION = "qa_validation"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"


class DubbingPipeline:
    def __init__(self):
        self._jobs: Dict[str, dict] = {}

    def create_job(self, tenant_id: str, source_url: str, source_lang: str = "en", target_lang: str = "de") -> dict:
        job_id = str(uuid4())
        job = {
            "id": job_id,
            "tenant_id": tenant_id,
            "source_url": source_url,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "status": PipelineStage.UPLOADED.value,
            "stages_completed": [],
            "quality_score": None,
            "created_at": datetime.utcnow().isoformat(),
            "output_url": None,
            "errors": [],
        }
        self._jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Optional[dict]:
        return self._jobs.get(job_id)

    def advance_stage(self, job_id: str) -> dict:
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError("Job not found")
        stages = [s.value for s in PipelineStage]
        current_idx = stages.index(job["status"])
        if current_idx < len(stages) - 2:
            next_stage = stages[current_idx + 1]
            job["status"] = next_stage
            job["stages_completed"].append(stages[current_idx])
        return job

    def run_qa(self, job_id: str) -> dict:
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError("Job not found")
        import random
        qa = {
            "lip_sync_score": round(random.uniform(0.85, 0.99), 2),
            "audio_quality_score": round(random.uniform(0.9, 0.99), 2),
            "translation_accuracy_score": round(random.uniform(0.88, 0.98), 2),
        }
        qa["overall_pass"] = all(v >= 0.85 for v in qa.values() if isinstance(v, float))
        qa["issues"] = [] if qa["overall_pass"] else ["Low score detected"]
        job["quality_score"] = round((qa["lip_sync_score"] + qa["audio_quality_score"] + qa["translation_accuracy_score"]) / 3, 2)
        job["qa_report"] = qa
        job["status"] = PipelineStage.QA_VALIDATION.value
        return qa

    def complete(self, job_id: str) -> dict:
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError("Job not found")
        job["status"] = PipelineStage.COMPLETED.value
        job["output_url"] = f"https://storage.example.com/output/{job_id}.mp4"
        job["completed_at"] = datetime.utcnow().isoformat()
        return job

    def fail(self, job_id: str, error: str):
        job = self._jobs.get(job_id)
        if job:
            job["status"] = PipelineStage.FAILED.value
            job["errors"].append(error)

    def list_jobs(self, tenant_id: str) -> List[dict]:
        return [j for j in self._jobs.values() if j["tenant_id"] == tenant_id]
