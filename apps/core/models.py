"""Domain models for Series Sync."""
from enum import Enum
from datetime import datetime
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


class QualityScore(str, Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"


class Tenant(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True


class SyncJob(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    source_language: str = "en"
    target_language: str = "de"
    status: JobStatus = JobStatus.UPLOADED
    source_video_url: str
    output_video_url: str | None = None
    quality_score: float | None = None
    qa_report: dict | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    source_audio: str | None = None
    transcription: str | None = None
    translation: str | None = None
    tts_audio: str | None = None
    final_video: str | None = None
    errors: list[str] = Field(default_factory=list)


class VoiceProfile(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    speaker_name: str
    voice_preset: str
    language: str = "de"
    reference_audio_url: str
    embedding: bytes | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_default: bool = False


class QAReport(BaseModel):
    job_id: UUID
    lip_sync_score: float
    audio_quality_score: float
    translation_accuracy_score: float
    overall_pass: bool
    issues: list[str] = Field(default_factory=list)
    notes: str | None = None
