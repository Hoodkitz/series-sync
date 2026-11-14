"""Tests for Gemini robustness, daily quota limits (MockGeminiTTS), and job resumption."""
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from apps.core.models import JobStatus
from apps.db.models import SyncJob, Tenant, VoiceProfile
from apps.media import storage
from apps.services.dubbing_pipeline import DubbingPipeline
from apps.services.providers import (
    FakeASR,
    FakeCloner,
    FakeTranslator,
    MockGeminiTTS,
    NoLipSync,
    ProviderError,
    Providers,
    QuotaExceeded,
)
from apps.services.worker import get_resumable_jobs, resume_pending_jobs


def gemini_mock_providers(tts_mock: MockGeminiTTS) -> Providers:
    return Providers(
        asr=FakeASR(),
        translator=FakeTranslator(),
        tts=tts_mock,
        lipsync=NoLipSync(),
        cloner=FakeCloner(),
    )


async def _setup_job(session_factory, sample_video, lines_count: int = 3):
    tid, jid, vid, up = uuid4(), uuid4(), uuid4(), uuid4()
    shutil.copy(sample_video, storage.uploads_dir(tid) / f"{up}.mp4")
    async with session_factory() as s:
        s.add(Tenant(id=tid, name="TestTenant"))
        s.add(VoiceProfile(id=vid, tenant_id=tid, speaker_name="S1", voice_preset="Kore",
                           reference_audio_url="", consent=True))
        job = SyncJob(
            id=jid,
            tenant_id=tid,
            source_video_url=f"upload:{up}",
            rights=True,
            errors=[],
            voice_profile_id=vid,
        )
        s.add(job)
        await s.commit()
    return tid, jid, vid


# -----------------------------------------------------------------------------
# 1. QuotaExceeded exception & MockGeminiTTS unit tests
# -----------------------------------------------------------------------------
def test_quota_exceeded_inheritance():
    assert issubclass(QuotaExceeded, ProviderError)
    err = QuotaExceeded("Daily limit reached")
    assert isinstance(err, ProviderError)


@pytest.mark.asyncio
async def test_mock_gemini_tts_daily_quota_and_reset(tmp_path):
    MockGeminiTTS.reset()
    tts = MockGeminiTTS(limit=2)
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    out1 = tmp_path / "line1.wav"
    out2 = tmp_path / "line2.wav"
    out3 = tmp_path / "line3.wav"

    # Call 1 and 2 succeed
    await tts.synthesize("Hello world", "Kore", "de", out1)
    assert out1.exists()
    assert MockGeminiTTS.get_calls_today() == 1

    await tts.synthesize("Second sentence", "Kore", "de", out2)
    assert out2.exists()
    assert MockGeminiTTS.get_calls_today() == 2

    # Call 3 exceeds daily quota of 2
    with pytest.raises(QuotaExceeded) as exc_info:
        await tts.synthesize("Third line should fail", "Kore", "de", out3)

    assert "daily quota limit (2/day) exceeded" in str(exc_info.value)
    assert today in str(exc_info.value)

    # Simulating explicit reset (or day change)
    MockGeminiTTS.reset()
    assert MockGeminiTTS.get_calls_today() == 0
    await tts.synthesize("Retry succeeds after reset", "Kore", "de", out3)
    assert out3.exists()
    assert MockGeminiTTS.get_calls_today() == 1


@pytest.mark.asyncio
async def test_mock_gemini_tts_day_rollover(tmp_path):
    MockGeminiTTS.reset()
    tts = MockGeminiTTS(limit=1)

    # Set calls for yesterday to limit
    yesterday = "2026-11-13"
    MockGeminiTTS.set_calls_today(1, today_key=yesterday)
    assert MockGeminiTTS.get_calls_today(yesterday) == 1

    # Today is fresh (0 calls)
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    assert MockGeminiTTS.get_calls_today(today) == 0

    out = tmp_path / "today.wav"
    await tts.synthesize("Line on new day", "Kore", "de", out)
    assert out.exists()
    assert MockGeminiTTS.get_calls_today(today) == 1


# -----------------------------------------------------------------------------
# 2. Pipeline behavior on QuotaExceeded: status=TTS_GENERATION, checkpoints saved
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_pipeline_pauses_on_quota_exceeded(session_factory, sample_video):
    MockGeminiTTS.reset()
    tid, jid, vid = await _setup_job(session_factory, sample_video)

    # limit=1 means the first segment succeeds, the second segment raises QuotaExceeded
    tts_mock = MockGeminiTTS(limit=1)
    p = gemini_mock_providers(tts_mock)
    pipeline = DubbingPipeline(session_factory, p)

    await pipeline.run_pipeline(jid, vid, tid)

    async with session_factory() as s:
        job = await s.get(SyncJob, jid)

    # Must be paused in TTS_GENERATION (not permanently FAILED)
    assert job.status == JobStatus.TTS_GENERATION.value
    assert any("quota" in e.lower() for e in (job.errors or []))

    # Finished lines should be preserved in job.segments
    assert len(job.segments) >= 2
    # First line was synthesized
    assert job.segments[0].get("fitted") is not None
    assert Path(job.segments[0]["fitted"]).exists()
    # Second line was not finished
    assert job.segments[1].get("fitted") is None


# -----------------------------------------------------------------------------
# 3. Pipeline resumption: finishes remaining lines without re-doing finished ones
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_pipeline_resumes_without_reprocessing(session_factory, sample_video):
    MockGeminiTTS.reset()
    tid, jid, vid = await _setup_job(session_factory, sample_video)

    # 1. Run with limit=1 -> pauses after first segment
    tts_mock = MockGeminiTTS(limit=1)
    pipeline = DubbingPipeline(session_factory, gemini_mock_providers(tts_mock))
    await pipeline.run_pipeline(jid, vid, tid)

    async with session_factory() as s:
        job = await s.get(SyncJob, jid)
        assert job.status == JobStatus.TTS_GENERATION.value
        first_line_fitted = job.segments[0]["fitted"]

    # 2. Quota is replenished (e.g. next day or reset)
    MockGeminiTTS.reset()

    # Track how many synthesize calls are made during resumption
    class CountingTTS(MockGeminiTTS):
        calls = 0

        async def synthesize(self, text, voice_id, lang, out_path):
            CountingTTS.calls += 1
            return await super().synthesize(text, voice_id, lang, out_path)

    resume_tts = CountingTTS(limit=10)
    resume_pipeline = DubbingPipeline(session_factory, gemini_mock_providers(resume_tts))
    await resume_pipeline.run_pipeline(jid, vid, tid)

    async with session_factory() as s:
        job = await s.get(SyncJob, jid)

    # Job is now completed
    assert job.status == JobStatus.COMPLETED.value
    assert job.final_video is not None
    assert Path(job.final_video).exists()
    assert job.qa_report["overall_pass"]

    # First line fitted audio was preserved, not re-synthesized
    assert job.segments[0]["fitted"] == first_line_fitted
    # The number of calls during resumption should be strictly less than total lines
    # because line 1 was already completed!
    assert CountingTTS.calls == len(job.segments) - 1


# -----------------------------------------------------------------------------
# 4. Worker discovery & automatic resumption
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_worker_discovers_and_resumes_quota_paused_job(session_factory, sample_video):
    MockGeminiTTS.reset()
    tid, jid, vid = await _setup_job(session_factory, sample_video)

    # Step 1: Run until QuotaExceeded
    tts_mock = MockGeminiTTS(limit=1)
    pipeline = DubbingPipeline(session_factory, gemini_mock_providers(tts_mock))
    await pipeline.run_pipeline(jid, vid, tid)

    async with session_factory() as s:
        job = await s.get(SyncJob, jid)
        assert job.status == JobStatus.TTS_GENERATION.value

    # Step 2: Verify get_resumable_jobs finds this job
    candidates = await get_resumable_jobs(session_factory, tenant_id=tid)
    candidate_ids = [c[0] for c in candidates]
    assert jid in candidate_ids

    # Step 3: Quota available, run worker resumption
    MockGeminiTTS.reset()
    worker_pipeline = DubbingPipeline(session_factory, gemini_mock_providers(MockGeminiTTS(limit=10)))
    resumed_count = await resume_pending_jobs(session_factory, pipeline=worker_pipeline, tenant_id=tid)
    assert resumed_count >= 1

    # Step 4: Verify the job is now completed
    async with session_factory() as s:
        job = await s.get(SyncJob, jid)
    assert job.status == JobStatus.COMPLETED.value
    assert job.final_video is not None
    assert Path(job.final_video).exists()


# -----------------------------------------------------------------------------
# 5. API endpoint /render resumes quota-paused jobs without 409 Conflict
# -----------------------------------------------------------------------------
def test_api_render_resumes_quota_paused_job(client, sample_video, session_factory):
    r = client.post("/auth/register", json={"email": "operator@example.com", "password": "correct-horse-battery"})
    assert r.status_code == 200
    r = client.post("/auth/token", data={"username": "operator@example.com", "password": "correct-horse-battery"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}

    with open(sample_video, "rb") as f:
        r = client.post("/uploads", headers=h, files={"file": ("ep1.mp4", f, "video/mp4")})
    assert r.status_code == 201
    up = r.json()["upload_id"]

    # Step 1: Run with MockGeminiTTS limit=1 to trigger quota exhaustion
    MockGeminiTTS.reset()
    tts_mock = MockGeminiTTS(limit=1)
    p = gemini_mock_providers(tts_mock)
    from apps.api.routers import pipeline as pipeline_router
    client.app.dependency_overrides[pipeline_router.get_pipeline] = lambda: DubbingPipeline(session_factory, p)

    r = client.post("/jobs", headers=h, json={"upload_id": up, "rights": True, "title": "Pilot", "target_language": "de"})
    assert r.status_code == 201
    job_id = r.json()["id"]

    job = client.get(f"/jobs/{job_id}", headers=h).json()
    assert job["status"] == "tts_generation"
    assert any("quota" in e.lower() for e in (job.get("errors") or []))

    # Step 2: Replenish quota and call POST /jobs/{job_id}/render
    MockGeminiTTS.reset()
    client.app.dependency_overrides[pipeline_router.get_pipeline] = lambda: DubbingPipeline(
        session_factory, gemini_mock_providers(MockGeminiTTS(limit=10))
    )

    r = client.post(f"/jobs/{job_id}/render", headers=h)
    assert r.status_code == 200, f"Expected 200 OK, got {r.status_code}: {r.text}"

    # Step 3: Verify the job resumed and finished successfully
    job = client.get(f"/jobs/{job_id}", headers=h).json()
    assert job["status"] == "completed"
    assert job["qa_report"]["overall_pass"]

