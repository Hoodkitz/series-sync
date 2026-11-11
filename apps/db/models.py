"""SQLAlchemy models."""
from sqlalchemy import UniqueConstraint, Column, String, DateTime, Boolean, ForeignKey, JSON, Text, Integer, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()

class Tenant(Base):
    __tablename__ = "tenants"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    users = relationship("User", back_populates="tenant")
    sync_jobs = relationship("SyncJob", back_populates="tenant")
    voice_profiles = relationship("VoiceProfile", back_populates="tenant")

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="user")
    is_active = Column(Boolean, default=True)

    tenant = relationship("Tenant", back_populates="users")

class SyncJob(Base):
    __tablename__ = "sync_jobs"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key", name="uq_sync_jobs_tenant_idem"),)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    source_language = Column(String(50), default="en")
    target_language = Column(String(50), default="de")
    status = Column(String(50), default="uploaded")
    source_video_url = Column(Text, nullable=False)
    output_video_url = Column(Text, nullable=True)
    voice_profile_id = Column(UUID(as_uuid=True), ForeignKey('voice_profiles.id'), nullable=True)
    rights = Column(Boolean, nullable=False, default=False, server_default="false")
    quality_score = Column(Float, nullable=True)
    qa_report = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    source_audio = Column(Text, nullable=True)
    transcription = Column(Text, nullable=True)
    translation = Column(Text, nullable=True)
    tts_audio = Column(Text, nullable=True)
    final_video = Column(Text, nullable=True)
    errors = Column(JSON, default=list)
    idempotency_key = Column(String(255), nullable=True)
    segments = Column(JSON, nullable=True)            # per-line timestamps, text, translation, dub audio, fit info
    duration_seconds = Column(Float, nullable=True)
    background_volume = Column(Float, nullable=True)  # original soundtrack level under the dub (0..1)
    title = Column(String(255), nullable=True)

    tenant = relationship("Tenant", back_populates="sync_jobs")

class VoiceProfile(Base):
    __tablename__ = "voice_profiles"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    speaker_name = Column(String(255), nullable=False)
    voice_preset = Column(String(255), nullable=False)
    language = Column(String(50), default="de")
    reference_audio_url = Column(Text, nullable=False)
    embedding = Column(Text, nullable=True)
    consent = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime, default=datetime.utcnow)
    is_default = Column(Boolean, default=False)

    tenant = relationship("Tenant", back_populates="voice_profiles")

