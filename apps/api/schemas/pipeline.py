"""Pydantic schemas for Series Sync pipeline."""
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from enum import Enum
from apps.core.models import JobStatus, QualityScore


class JobCreate(BaseModel):
    rights: bool
    voice_profile_id: UUID
    tenant_id: UUID
    source_video_url: str
    source_language: str = "en"
    target_language: str = "de"


class JobResponse(BaseModel):
    id: str
    tenant_id: UUID
    source_language: str
    target_language: str
    status: str
    source_video_url: str
    output_video_url: str | None
    quality_score: float | None
    qa_report: dict | None
    source_audio: str | None
    transcription: str | None
    translation: str | None
    tts_audio: str | None
    final_video: str | None
    errors: list[str]
    created_at: datetime
    completed_at: datetime | None

    class Config:
        from_attributes = True


class JobListResponse(BaseModel):
    jobs: list[JobResponse]


class StageAdvance(BaseModel):
    stage: str


class StageResponse(BaseModel):
    id: str
    tenant_id: UUID
    status: str
    source_language: str
    target_language: str
    source_video_url: str
    output_video_url: str | None
    quality_score: float | None
    created_at: datetime
    completed_at: datetime | None
    errors: list[str]

    class Config:
        from_attributes = True


class QAReportCreate(BaseModel):
    job_id: str
    lip_sync_score: float = Field(ge=0.0, le=1.0)
    audio_quality_score: float = Field(ge=0.0, le=1.0)
    translation_accuracy_score: float = Field(ge=0.0, le=1.0)
    overall_pass: bool
    issues: list[str] = Field(default_factory=list)
    notes: str | None = None


class QAReportResponse(BaseModel):
    job_id: str
    lip_sync_score: float
    audio_quality_score: float
    translation_accuracy_score: float
    overall_pass: bool
    issues: list[str]
    notes: str | None


class VoiceCreate(BaseModel):
    consent: bool
    tenant_id: UUID
    speaker_name: str
    voice_preset: str
    language: str = "de"
    reference_audio_url: str
    embedding: bytes | None = None
    is_default: bool = False


class VoiceResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    speaker_name: str
    voice_preset: str
    language: str
    reference_audio_url: str
    embedding: bytes | None
    is_default: bool
    created_at: datetime

    class Config:
        from_attributes = True


class VoiceListResponse(BaseModel):
    voices: list[VoiceResponse]


class StatsResponse(BaseModel):
    tenant_id: str
    completed_jobs: int
    total_jobs: int
    jobs: list[dict]
