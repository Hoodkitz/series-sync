"""End-to-end pipeline with fake AI providers but real ffmpeg: timing fit, mixing, muxing, QA, resume."""
import shutil
from uuid import uuid4

import pytest

from apps.core.models import JobStatus
from apps.db.models import SyncJob, Tenant, VoiceProfile
from apps.media import ffmpeg, storage
from apps.services.dubbing_pipeline import DubbingPipeline
from apps.services.providers import FakeASR, FakeTranslator, FakeTTS, NoLipSync, FakeCloner, Providers


def providers(**kw):
    base = dict(asr=FakeASR(), translator=FakeTranslator(), tts=FakeTTS(), lipsync=NoLipSync(), cloner=FakeCloner())
    base.update(kw)
    return Providers(**base)


async def _setup(sf, sample_video, rights=True, consent=True, with_voice=True):
    tid, jid, vid, up = uuid4(), uuid4(), uuid4(), uuid4()
    shutil.copy(sample_video, storage.uploads_dir(tid) / f"{up}.mp4")
    async with sf() as s:
        s.add(Tenant(id=tid, name="T"))
        if with_voice:
            s.add(VoiceProfile(id=vid, tenant_id=tid, speaker_name="A", voice_preset="voiceabc123",
                               reference_audio_url="", consent=consent))
        s.add(SyncJob(id=jid, tenant_id=tid, source_video_url=f"upload:{up}", rights=rights, errors=[],
                      voice_profile_id=vid if with_voice else None))
        await s.commit()
    return tid, jid, vid


@pytest.mark.asyncio
async def test_full_dub(session_factory, sample_video):
    tid, jid, vid = await _setup(session_factory, sample_video)
    await DubbingPipeline(session_factory, providers()).run_pipeline(jid, vid, tid)
    async with session_factory() as s:
        job = await s.get(SyncJob, jid)
    assert job.status == JobStatus.COMPLETED.value, job.errors
    assert len(job.segments) >= 3
    assert all(seg["translation"].startswith("Zeile") for seg in job.segments)
    # German lines are longer than their slots -> sped up, but never beyond MAX_TEMPO
    assert any(seg["tempo"] > 1.0 for seg in job.segments)
    assert all(seg["tempo"] <= 1.3 for seg in job.segments)
    info = await ffmpeg.media_info(job.final_video)
    assert info["has_video"] and info["has_audio"]
    assert abs(info["duration"] - 8.0) < 1.0
    probe = await ffmpeg.probe(job.final_video)
    audio = [st for st in probe["streams"] if st["codec_type"] == "audio"]
    assert len(audio) == 2  # dub (default) + original
    assert audio[0]["tags"]["language"] == "ger"
    assert "AI-generated" in probe["format"]["tags"]["comment"]
    assert job.qa_report["overall_pass"] and job.quality_score > 0.9
    assert job.output_video_url == f"/jobs/{jid}/output"


@pytest.mark.asyncio
async def test_missing_rights(session_factory, sample_video):
    tid, jid, vid = await _setup(session_factory, sample_video, rights=False)
    await DubbingPipeline(session_factory, providers()).run_pipeline(jid, vid, tid)
    async with session_factory() as s:
        job = await s.get(SyncJob, jid)
    assert job.status == "failed" and "Missing rights for this content." in job.errors


@pytest.mark.asyncio
async def test_missing_consent(session_factory, sample_video):
    tid, jid, vid = await _setup(session_factory, sample_video, consent=False)
    await DubbingPipeline(session_factory, providers()).run_pipeline(jid, vid, tid)
    async with session_factory() as s:
        job = await s.get(SyncJob, jid)
    assert job.status == "failed" and "Voice profile missing or no consent provided." in job.errors


@pytest.mark.asyncio
async def test_foreign_tenant_voice_is_rejected(session_factory, sample_video):
    tid, jid, _ = await _setup(session_factory, sample_video, with_voice=False)
    _, _, foreign_voice = await _setup(session_factory, sample_video)
    await DubbingPipeline(session_factory, providers()).run_pipeline(jid, foreign_voice, tid)
    async with session_factory() as s:
        job = await s.get(SyncJob, jid)
    assert job.status == "failed"


@pytest.mark.asyncio
async def test_crash_resumes_without_repeating_paid_steps(session_factory, sample_video):
    tid, jid, vid = await _setup(session_factory, sample_video)

    class Boom(FakeTTS):
        async def synthesize(self, *a, **k):
            raise RuntimeError("tts down")

    class CountingASR(FakeASR):
        calls = 0

        async def transcribe(self, *a, **k):
            CountingASR.calls += 1
            return await super().transcribe(*a, **k)

    await DubbingPipeline(session_factory, providers(asr=CountingASR(), tts=Boom())).run_pipeline(jid, vid, tid)
    async with session_factory() as s:
        job = await s.get(SyncJob, jid)
        assert job.status == "failed" and job.segments and job.segments[0]["translation"]
        assert "Internal processing error" in job.errors[-1] and "tts down" not in job.errors[-1]
        job.status = "uploaded"
        await s.commit()
    await DubbingPipeline(session_factory, providers(asr=CountingASR())).run_pipeline(jid, vid, tid)
    async with session_factory() as s:
        job = await s.get(SyncJob, jid)
    assert job.status == "completed"
    assert CountingASR.calls == 1


@pytest.mark.asyncio
async def test_untranslated_lines_go_to_human_review(session_factory, sample_video):
    tid, jid, vid = await _setup(session_factory, sample_video)

    class Lazy(FakeTranslator):
        async def translate(self, segments, source, target):
            return [s["text"] for s in segments]  # returns the source text unchanged

    await DubbingPipeline(session_factory, providers(translator=Lazy())).run_pipeline(jid, vid, tid)
    async with session_factory() as s:
        job = await s.get(SyncJob, jid)
    assert job.status == JobStatus.HITL_REVIEW.value
    assert job.qa_report["translation_accuracy_score"] == 0
    assert job.qa_report["issues"]


@pytest.mark.asyncio
async def test_source_must_be_own_upload(session_factory):
    tid, jid = uuid4(), uuid4()
    async with session_factory() as s:
        s.add(Tenant(id=tid, name="T"))
        s.add(SyncJob(id=jid, tenant_id=tid, source_video_url="/etc/passwd", rights=True, errors=[]))
        await s.commit()
    await DubbingPipeline(session_factory, providers()).run_pipeline(jid, None, tid)
    async with session_factory() as s:
        job = await s.get(SyncJob, jid)
    assert job.status == "failed" and "Source upload not found." in job.errors


@pytest.mark.asyncio
async def test_consent_revoked_mid_run_leaves_nothing(session_factory, sample_video):
    tid, jid, vid = await _setup(session_factory, sample_video)

    class RevokingTTS(FakeTTS):
        async def synthesize(self, text, voice_id, language, out_path):
            async with session_factory() as s:  # consent is withdrawn while lines are being voiced
                v = await s.get(VoiceProfile, vid)
                if v is not None:
                    await s.delete(v)
                    job = await s.get(SyncJob, jid)
                    job.status = "failed"
                    job.errors = (job.errors or []) + ["voice consent revoked: dub deleted"]
                    await s.commit()
            return await super().synthesize(text, voice_id, language, out_path)

    await DubbingPipeline(session_factory, providers(tts=RevokingTTS())).run_pipeline(jid, vid, tid)
    async with session_factory() as s:
        job = await s.get(SyncJob, jid)
    assert job.status == "failed" and job.final_video is None
    assert not (storage.tenant_dir(tid) / "jobs" / str(jid)).exists()


@pytest.mark.asyncio
async def test_playlist_container_rejected(tmp_path):
    from apps.media.ffmpeg import MediaError, media_info
    target = tmp_path / "secret.txt"
    target.write_text("top secret")
    pl = tmp_path / "evil.m3u8"
    pl.write_text(f"#EXTM3U\n#EXTINF:1,\nfile://{target}\n#EXT-X-ENDLIST\n")
    with pytest.raises(MediaError):
        await media_info(pl)


@pytest.mark.asyncio
async def test_identical_short_lines_and_edits_do_not_force_review(session_factory, sample_video):
    tid, jid, vid = await _setup(session_factory, sample_video)

    class Names(FakeTranslator):
        async def translate(self, segments, source, target):
            return ["Okay." if i == 0 else f"Zeile {i + 1}, weißt du?" for i, _ in enumerate(segments)]

    class OkayASR(FakeASR):
        async def transcribe(self, *a, **k):
            tr = await super().transcribe(*a, **k)
            tr.segments[0]["text"] = "Okay."
            return tr

    await DubbingPipeline(session_factory, providers(asr=OkayASR(), translator=Names())).run_pipeline(jid, vid, tid)
    async with session_factory() as s:
        job = await s.get(SyncJob, jid)
    assert job.qa_report["translation_accuracy_score"] == 1.0


@pytest.mark.asyncio
async def test_deleted_voice_mid_run_fails_instead_of_hanging(session_factory, sample_video):
    tid, jid, vid = await _setup(session_factory, sample_video)

    class DeletingTTS(FakeTTS):
        async def synthesize(self, text, voice_id, language, out_path):
            async with session_factory() as s:
                v = await s.get(VoiceProfile, vid)
                if v is not None:
                    await s.delete(v)
                    await s.commit()
            return await super().synthesize(text, voice_id, language, out_path)

    await DubbingPipeline(session_factory, providers(tts=DeletingTTS())).run_pipeline(jid, vid, tid)
    async with session_factory() as s:
        job = await s.get(SyncJob, jid)
    assert job.status == "failed"


def test_retry_delay_honours_provider_hint():
    import httpx
    from apps.services.providers import _retry_delay
    r = httpx.Response(429, text="Please retry in 12.5s.", request=httpx.Request("POST", "https://x"))
    assert _retry_delay(r, 0) == 12.5
    r = httpx.Response(503, headers={"retry-after": "300"}, request=httpx.Request("POST", "https://x"))
    assert _retry_delay(r, 0) == 65.0


@pytest.mark.asyncio
async def test_dub_track_is_full_length_and_original_voice_is_muted(session_factory, sample_video):
    tid, jid, vid = await _setup(session_factory, sample_video)
    await DubbingPipeline(session_factory, providers()).run_pipeline(jid, vid, tid)
    async with session_factory() as s:
        job = await s.get(SyncJob, jid)
    probe = await ffmpeg.probe(job.final_video)
    audio = [st for st in probe["streams"] if st["codec_type"] == "audio"]
    assert float(audio[0]["duration"]) > 7.5  # was cut ~3 s early by -shortest + loudnorm latency
    # background under a spoken line is silent: ducking envelope check on the helper
    import numpy as np, wave
    from pathlib import Path
    src = Path(job.final_video).with_name("bgtest.wav")
    await ffmpeg.to_wav(sample_video, src)
    out = ffmpeg.duck_background(src, src.with_name("bgtest_d.wav"), [(2.0, 4.0)], 0.2)
    data = ffmpeg.read_wav(out).astype(np.int32)
    sr = ffmpeg.SAMPLE_RATE
    assert np.abs(data[int(2.5 * sr):int(3.5 * sr)]).max() == 0
    assert np.abs(data[int(5.5 * sr):int(6.5 * sr)]).max() > 0
