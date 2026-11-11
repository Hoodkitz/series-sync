import pytest_asyncio
pytest_plugins = ("pytest_asyncio",)
import pytest
import os
import asyncio
from uuid import uuid4

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from apps.db.models import Base, Tenant, SyncJob, VoiceProfile
from apps.api.routers.voices import revoke_consent

@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()

@pytest.mark.asyncio
async def test_revoke_consent(session_factory):
    tenant_id = uuid4()
    job_id = uuid4()
    voice_id = uuid4()

    # Create dummy files
    dummy_ref = "dummy_ref.wav"
    dummy_tts = "dummy_tts.wav"
    with open(dummy_ref, "w") as f:
        f.write("ref")
    with open(dummy_tts, "w") as f:
        f.write("tts")

    async with session_factory() as session:
        tenant = Tenant(id=tenant_id, name="Test Tenant")
        session.add(tenant)

        voice = VoiceProfile(id=voice_id, tenant_id=tenant_id, speaker_name="Test", voice_preset="preset", reference_audio_url=dummy_ref, consent=True)
        session.add(voice)

        job = SyncJob(id=job_id, tenant_id=tenant_id, source_video_url="test.mp4", rights=True, voice_profile_id=voice_id, tts_audio=dummy_tts)
        session.add(job)

        await session.commit()

    async with session_factory() as session:
        await revoke_consent(voice_id=voice_id, current_user=None, session=session)

    # Check files are deleted
    assert not os.path.exists(dummy_ref)
    assert not os.path.exists(dummy_tts)

    # Check DB
    async with session_factory() as session:
        voice = await session.get(VoiceProfile, voice_id)
        assert voice is None

        job = await session.get(SyncJob, job_id)
        assert job.tts_audio is None
