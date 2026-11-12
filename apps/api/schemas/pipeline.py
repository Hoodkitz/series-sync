"""Pydantic schemas for Series Sync pipeline."""
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
from uuid import UUID
from datetime import datetime
from enum import Enum
from apps.core.models import JobStatus, QualityScore


class JobCreate(BaseModel):
    upload_id: UUID
    rights: bool = Field(description="Customer confirms it holds the rights to dub this content")
    voice_profile_id: Optional[UUID] = None  # None = stock voice
    source_language: str = Field("auto", pattern=r"^(auto|[a-z]{2})$")
    target_language: str = Field("de", pattern=r"^[a-z]{2}$")
    title: Optional[str] = Field(None, max_length=255)
    background_volume: Optional[float] = Field(None, ge=0.0, le=1.0)
    idempotency_key: Optional[str] = Field(None, max_length=255)


class UploadResponse(BaseModel):
    upload_id: UUID
    filename: str
    size_bytes: int
    duration_seconds: float


class SegmentEdit(BaseModel):
    translation: str = Field(min_length=0, max_length=2000)


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None = None
    source_language: str
    target_language: str
    status: str
    output_video_url: str | None = None
    voice_profile_id: UUID | None = None
    quality_score: float | None = None
    qa_report: dict | None = None
    duration_seconds: float | None = None
    transcription: str | None = None
    translation: str | None = None
    errors: list[str] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime | None = None

    @field_validator("errors", mode="before")
    @classmethod
    def _none_is_empty(cls, v):
        return v or []


class JobListResponse(BaseModel):
    jobs: list[JobResponse]


class VoiceCreate(BaseModel):
    """Register a stock/provider voice by id (no voice cloning)."""
    speaker_name: str = Field(min_length=1, max_length=255)
    voice_preset: str = Field(pattern=r"^[A-Za-z0-9]{3,64}$",
                              description="Provider voice id (ElevenLabs id, or a Gemini voice name such as 'Kore')")
    language: str = Field("de", pattern=r"^[a-z]{2}$")
    consent: bool = Field(description="Licence/consent for this voice is documented")
    is_default: bool = False


class VoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    speaker_name: str
    voice_preset: str
    language: str
    consent: bool
    cloned: bool = False
    is_default: bool
    created_at: datetime


class VoiceListResponse(BaseModel):
    voices: list[VoiceResponse]


class StatsResponse(BaseModel):
    total_jobs: int
    completed_jobs: int
    in_review: int
    failed: int
    processing: int
    minutes_dubbed: float
