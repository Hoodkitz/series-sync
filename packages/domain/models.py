"""Domain models for Series Sync SaaS."""
from enum import Enum
from datetime import datetime
from typing import Optional, List
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


class JobStatus(str, Enum):
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


class Tenant(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SyncJob(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    source_language: str = "en"
    target_language: str = "de"
    status: JobStatus = JobStatus.UPLOADED
    source_video_url: str
    output_video_url: Optional[str] = None
    quality_score: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


class VoiceProfile(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    speaker_name: str
    reference_audio_url: str
    embedding: bytes
    created_at: datetime = Field(default_factory=datetime.utcnow)


class QAReport(BaseModel):
    job_id: UUID
    lip_sync_score: float
    audio_quality_score: float
    translation_accuracy_score: float
    overall_pass: bool
    issues: List[str] = []
