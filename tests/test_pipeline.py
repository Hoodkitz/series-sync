import pytest_asyncio
pytest_plugins = ("pytest_asyncio",)
import pytest
import asyncio
from uuid import uuid4
from datetime import datetime

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from apps.db.models import Base, Tenant, SyncJob, VoiceProfile
from apps.services.dubbing_pipeline import DubbingPipeline
from apps.core.models import JobStatus
from apps.services.fakes.asr import FakeASRService
from apps.services.fakes.translation import FakeTranslationService
from apps.services.fakes.tts import FakeTTSService
from apps.services.fakes.lipsync import FakeLipSyncService
from apps.services.fakes.qa import FakeQAService

@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()

@pytest.mark.asyncio
async def test_pipeline_success(session_factory):
    tenant_id = uuid4()
    job_id = uuid4()
    voice_id = uuid4()

    async with session_factory() as session:
        tenant = Tenant(id=tenant_id, name="Test Tenant")
        session.add(tenant)
        job = SyncJob(id=job_id, tenant_id=tenant_id, source_video_url="test.mp4", rights=True)
        session.add(job)
        voice = VoiceProfile(id=voice_id, tenant_id=tenant_id, speaker_name="Test", voice_preset="preset", reference_audio_url="ref.wav", consent=True)
        session.add(voice)
        await session.commit()

    pipeline = DubbingPipeline(
        asr=FakeASRService(),
        translator=FakeTranslationService(),
        tts=FakeTTSService(),
        lipsync=FakeLipSyncService(),
        qa=FakeQAService(),
        session_factory=session_factory
    )

    await pipeline.run_pipeline(job_id, voice_id)

    async with session_factory() as session:
        updated_job = await session.get(SyncJob, job_id)
        assert updated_job.status == JobStatus.COMPLETED.value
        assert updated_job.transcription == "Fake transcription text"
        assert updated_job.translation == "Fake translated text"
        assert updated_job.tts_audio == "fake_tts_audio.wav"
        assert updated_job.final_video == "fake_lipsync_video.mp4"
        assert updated_job.qa_report is not None
        assert updated_job.quality_score is not None

@pytest.mark.asyncio
async def test_pipeline_missing_rights(session_factory):
    tenant_id = uuid4()
    job_id = uuid4()
    voice_id = uuid4()

    async with session_factory() as session:
        tenant = Tenant(id=tenant_id, name="Test Tenant")
        session.add(tenant)
        job = SyncJob(id=job_id, tenant_id=tenant_id, source_video_url="test.mp4", rights=False)
        session.add(job)
        voice = VoiceProfile(id=voice_id, tenant_id=tenant_id, speaker_name="Test", voice_preset="preset", reference_audio_url="ref.wav", consent=True)
        session.add(voice)
        await session.commit()

    pipeline = DubbingPipeline(
        asr=FakeASRService(),
        translator=FakeTranslationService(),
        tts=FakeTTSService(),
        lipsync=FakeLipSyncService(),
        qa=FakeQAService(),
        session_factory=session_factory
    )

    await pipeline.run_pipeline(job_id, voice_id)

    async with session_factory() as session:
        updated_job = await session.get(SyncJob, job_id)
        assert updated_job.status == JobStatus.FAILED.value
        assert "Missing rights for this content." in updated_job.errors

@pytest.mark.asyncio
async def test_pipeline_missing_consent(session_factory):
    tenant_id = uuid4()
    job_id = uuid4()
    voice_id = uuid4()

    async with session_factory() as session:
        tenant = Tenant(id=tenant_id, name="Test Tenant")
        session.add(tenant)
        job = SyncJob(id=job_id, tenant_id=tenant_id, source_video_url="test.mp4", rights=True)
        session.add(job)
        voice = VoiceProfile(id=voice_id, tenant_id=tenant_id, speaker_name="Test", voice_preset="preset", reference_audio_url="ref.wav", consent=False)
        session.add(voice)
        await session.commit()

    pipeline = DubbingPipeline(
        asr=FakeASRService(),
        translator=FakeTranslationService(),
        tts=FakeTTSService(),
        lipsync=FakeLipSyncService(),
        qa=FakeQAService(),
        session_factory=session_factory
    )

    await pipeline.run_pipeline(job_id, voice_id)

    async with session_factory() as session:
        updated_job = await session.get(SyncJob, job_id)
        assert updated_job.status == JobStatus.FAILED.value
        assert "Voice profile missing or no consent provided." in updated_job.errors
