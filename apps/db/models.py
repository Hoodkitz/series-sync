"""SQLAlchemy models."""
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, JSON, Text, Integer, Float
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
    created_at = Column(DateTime, server_default="NOW()")
    is_active = Column(Boolean, default=True)


class SyncJob(Base):
    __tablename__ = "sync_jobs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    source_language = Column(String(50), default="en")
    target_language = Column(String(50), default="de")
    status = Column(String(50), default="uploaded")
    source_video_url = Column(Text, nullable=False)
    output_video_url = Column(Text, nullable=True)
    quality_score = Column(Float, nullable=True)
    qa_report = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default="NOW()")
    completed_at = Column(DateTime, nullable=True)
    source_audio = Column(Text, nullable=True)
    transcription = Column(Text, nullable=True)
    translation = Column(Text, nullable=True)
    tts_audio = Column(Text, nullable=True)
    final_video = Column(Text, nullable=True)
    errors = Column(JSON, default=list)
    tenant = relationship("Tenant", back_populates="sync_jobs")
    sync_jobs = relationship("SyncJob", back_populates="tenant")
    voice_profiles = relationship("VoiceProfile", back_populates="tenant")
    voice_profiles = relationship("VoiceProfile", back_populates="tenant")


class VoiceProfile(Base):
    __tablename__ = "voice_profiles"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    speaker_name = Column(String(255), nullable=False)
    voice_preset = Column(String(255), nullable=False)
    language = Column(String(50), default="de")
    reference_audio_url = Column(Text, nullable=False)
    embedding = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default="NOW()")
    is_default = Column(Boolean, default=False)
    tenant = relationship("Tenant", back_populates="voice_profiles")


    voice_profiles = relationship("VoiceProfile", back_populates="tenant")
