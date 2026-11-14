"""Dubbing pipeline: upload -> transcript (with timestamps) -> dubbing translation -> per-line speech synthesis ->
timing fit -> mix & mux -> automatic QA.

Every stage checkpoints its result on the job row (``segments`` JSON + file paths inside the job directory), so a
crashed or edited job resumes at the first missing piece instead of paying for ASR/TTS again.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm.attributes import flag_modified

from apps.core.config import settings
from apps.core.models import JobStatus
from apps.db.models import SyncJob, VoiceProfile
from apps.media import ffmpeg, storage
from apps.services.providers import (
    ProviderError,
    Providers,
    QuotaExceeded,
    default_providers,
)

log = logging.getLogger("seriessync.pipeline")

MAX_TEMPO = 1.30          # speed-up beyond this sounds rushed; such lines are flagged for human review
GAP = 0.05                # minimum silence between two lines
OVERRUN_TOLERANCE = 0.25  # seconds a line may spill into the next slot before QA flags it

_running: set[UUID] = set()


class PipelineAbort(Exception):
    """Stop the run without marking an error (e.g. job cancelled meanwhile)."""


class DubbingPipeline:
    def __init__(self, session_factory, providers: Providers | None = None):
        self.session_factory = session_factory
        self.p = providers or default_providers()
        self._voices: dict[UUID, UUID] = {}  # job id -> voice profile used by the current run

    # ------------------------------------------------------------------ entry point
    async def run_pipeline(self, job_id: UUID, voice_profile_id: UUID | None = None,
                           tenant_id: UUID | None = None) -> None:
        job_id = UUID(str(job_id))
        if job_id in _running:
            return  # already being processed in this worker
        _running.add(job_id)
        try:
            await self._run(job_id, voice_profile_id, tenant_id)
        finally:
            _running.discard(job_id)
            self._voices.pop(job_id, None)

    async def _run(self, job_id: UUID, voice_profile_id, tenant_id) -> None:
        from apps.db.session import set_tenant_context

        async with self.session_factory() as session:
            if tenant_id is not None:
                await set_tenant_context(session, tenant_id)
            job = await session.get(SyncJob, job_id)
            if not job:
                raise ValueError("Job not found")
            if job.status in (JobStatus.COMPLETED.value, JobStatus.HITL_REVIEW.value) and job.final_video:
                return  # idempotent: finished jobs are never re-rendered unless an edit reset them
            if voice_profile_id is None:
                voice_profile_id = job.voice_profile_id

            async def fail(msg: str) -> None:
                job.status = JobStatus.FAILED.value
                job.errors = (job.errors or []) + [msg]
                await session.commit()

            if not job.rights:
                return await fail("Missing rights for this content.")

            voice_id = settings.TTS_DEFAULT_VOICE
            if voice_profile_id is not None:
                voice = await session.get(VoiceProfile, voice_profile_id)
                if voice is not None and voice.tenant_id != job.tenant_id:
                    voice = None  # never use a voice that belongs to another tenant
                if not voice or not voice.consent:
                    return await fail("Voice profile missing or no consent provided.")
                job.voice_profile_id = voice.id
                voice_id = voice.voice_preset
                self._voices[job.id] = voice.id

            source = storage.resolve_source(job.tenant_id, job.source_video_url)
            if source is None:
                return await fail("Source upload not found.")
            job_tenant = job.tenant_id
            workdir = storage.job_dir(job_tenant, job.id)

            try:
                await self._stages(session, job, source, workdir, voice_id)
            except PipelineAbort:
                # Cancelled or consent revoked while running: nothing produced after that point may survive.
                await session.rollback()
                if tenant_id is not None:
                    await set_tenant_context(session, tenant_id)
                job = await session.get(SyncJob, job_id, populate_existing=True)
                if job is None or any("consent revoked" in e for e in (job.errors or [])):
                    storage.delete_job_files(job_tenant, job_id)
                elif job.status not in (JobStatus.FAILED.value, JobStatus.EDITED.value):
                    # aborted for another reason (e.g. the voice was deleted): never leave it "processing"
                    job.status = JobStatus.FAILED.value
                    job.errors = (job.errors or []) + ["Voice profile no longer available – choose a voice and retry."]
                    await session.commit()
                return
            except Exception as e:  # checkpointed: a retry resumes at the failed stage
                log.exception("job %s failed", job_id)
                await session.rollback()
                if tenant_id is not None:
                    await set_tenant_context(session, tenant_id)
                job = await session.get(SyncJob, job_id)
                if job is not None:
                    if isinstance(e, QuotaExceeded):
                        # Temporary provider quota exhausted (e.g. Gemini free-tier mock limit).
                        # Leave the job in the TTS generation state so the worker can retry later.
                        job.status = JobStatus.TTS_GENERATION.value
                        job.errors = (job.errors or []) + [str(e)[:500]]
                        await session.commit()
                    else:
                        job.status = JobStatus.FAILED.value
                        job.errors = (job.errors or []) + [_public_error(e)]
                        await session.commit()

    # ------------------------------------------------------------------ stages
    async def _ensure_still_wanted(self, session, job: SyncJob) -> None:
        """Abort if someone else ended the job meanwhile (cancel, consent revocation, deletion)."""
        await session.refresh(job, ["status", "errors", "voice_profile_id"])
        if job.status in (JobStatus.FAILED.value, JobStatus.EDITED.value):
            raise PipelineAbort()  # cancelled, or a human edited lines meanwhile: this run's data is stale
        voice_pk = self._voices.get(job.id)
        if voice_pk is not None:
            voice = await session.get(VoiceProfile, voice_pk, populate_existing=True)
            if voice is None or not voice.consent:
                raise PipelineAbort()

    async def _set_status(self, session, job: SyncJob, status: JobStatus) -> None:
        await self._ensure_still_wanted(session, job)
        job.status = status.value
        await session.commit()

    async def _save_segments(self, session, job: SyncJob, segments: list[dict]) -> None:
        job.segments = segments
        flag_modified(job, "segments")
        await session.commit()

    async def _stages(self, session, job: SyncJob, source: Path, workdir: Path, voice_id: str) -> None:
        # 1. Preprocessing: validate media, extract speech-optimised audio
        info = await ffmpeg.media_info(source)
        if not info["has_video"]:
            raise ProviderError("The upload contains no video stream.")
        if not info["has_audio"]:
            raise ProviderError("The upload contains no audio track to dub.")
        if info["duration"] > settings.MAX_DURATION_MINUTES * 60:
            raise ProviderError(f"Video longer than {settings.MAX_DURATION_MINUTES} minutes.")
        asr_audio = workdir / "speech.mp3"
        if not job.source_audio or not Path(job.source_audio).exists():
            await self._set_status(session, job, JobStatus.PREPROCESSING)
            await ffmpeg.extract_audio_for_asr(source, asr_audio, settings.MAX_DURATION_MINUTES * 60)
            job.source_audio = str(asr_audio)
            job.duration_seconds = info["duration"]
            await session.commit()

        # 2. Transcription with timestamps
        segments: list[dict] = [dict(s) for s in (job.segments or [])]
        if not segments:
            await self._set_status(session, job, JobStatus.TRANSCRIPTION)
            lang = None if job.source_language in (None, "", "auto") else job.source_language
            tr = await self.p.asr.transcribe(Path(job.source_audio), lang)
            if not tr.segments:
                raise ProviderError("No speech detected in the video.")
            if lang is None:
                job.source_language = tr.language
            segments = [dict(s) for s in tr.segments]
            if job.voice_profile_id is None and hasattr(self.p.tts, "auto_voices"):
                # no voice chosen: give every detected speaker an own voice of matching gender
                voices = self.p.tts.auto_voices(segments)
                for seg in segments:
                    seg["voice"] = voices.get(seg.get("speaker", "S1"))
            job.transcription = "\n".join(s["text"] for s in segments)
            await self._save_segments(session, job, segments)

        # 3. Dubbing translation (only lines that do not have one yet, e.g. after an edit reset)
        todo = [i for i, s in enumerate(segments) if not s.get("translation") and not s.get("edited")]
        if todo:
            await self._set_status(session, job, JobStatus.TRANSLATION)
            lines = await self.p.translator.translate([segments[i] for i in todo], job.source_language,
                                                      job.target_language)
            for i, t in zip(todo, lines):
                segments[i]["translation"] = t
            job.translation = "\n".join(s.get("translation", "") for s in segments)
            await self._save_segments(session, job, segments)

        # 4. Speech synthesis per line + timing fit into the original slot
        todo = [i for i, s in enumerate(segments) if not (s.get("fitted") and Path(s["fitted"]).exists())]
        if todo:
            await self._set_status(session, job, JobStatus.TTS_GENERATION)
            sem = asyncio.Semaphore(settings.TTS_CONCURRENCY)

            async def one(i: int) -> None:
                async with sem:
                    await self._synth_and_fit(segments, i, workdir, voice_id, job.target_language, info["duration"])

            results = await asyncio.gather(*(one(i) for i in todo), return_exceptions=True)
            await self._save_segments(session, job, segments)  # keep finished lines even if one failed
            errors = [r for r in results if isinstance(r, Exception)]
            if errors:
                raise errors[0]
            job.tts_audio = str(workdir / "segments")
            job.final_video = None  # new audio -> must re-render
            await session.commit()

        # 5. Assemble the dub track, optional lip-sync, mix with the original soundtrack and mux
        if not job.final_video or not Path(job.final_video).exists():
            await self._set_status(session, job, JobStatus.RENDERING)
            dub = workdir / "dub_track.wav"
            ffmpeg.assemble_track([(s["fitted"], s["start"]) for s in segments], info["duration"], dub)
            video = source
            if self.p.lipsync.name != "none":
                await self._set_status(session, job, JobStatus.LIP_SYNC)
                video = await self.p.lipsync.apply(source, dub, workdir / "lipsync.mp4")
            out = workdir / "output.mp4"
            bg = job.background_volume if job.background_volume is not None else settings.BACKGROUND_VOLUME
            await ffmpeg.mux_dub(video, dub, out, background_volume=bg,
                                 target_language=job.target_language, source_language=job.source_language,
                                 speech=[(s["start"], s["end"]) for s in segments])
            job.final_video = str(out)
            job.output_video_url = f"/jobs/{job.id}/output"
            job.qa_report = None
            await session.commit()

        # 6. Automatic QA -> completed, or human review when something is off
        await self._set_status(session, job, JobStatus.QA_VALIDATION)
        report = await self.qa(segments, Path(job.final_video), info["duration"])
        await self._ensure_still_wanted(session, job)
        job.qa_report = report
        job.quality_score = report["quality_score"]
        job.status = (JobStatus.COMPLETED if report["overall_pass"] else JobStatus.HITL_REVIEW).value
        job.completed_at = datetime.utcnow()
        await session.commit()

    async def _synth_and_fit(self, segments: list[dict], i: int, workdir: Path, voice_id: str, lang: str,
                             total: float) -> None:
        seg = segments[i]
        segdir = workdir / "segments"
        segdir.mkdir(exist_ok=True)
        raw = segdir / f"{i:05d}_raw.wav"
        fitted = segdir / f"{i:05d}.wav"
        text = (seg.get("translation") or "").strip()
        if not text:
            await ffmpeg.synth_tone(fitted, 0.05, freq=1)  # an empty line stays (practically) silent
            seg.update(fitted=str(fitted), tempo=1.0, dub_seconds=0.0, slot=0.0, overrun=0.0)
            return
        await self.p.tts.synthesize(text, seg.get("voice") or voice_id, lang, raw)
        raw_dur = ffmpeg.wav_duration(raw)
        next_start = segments[i + 1]["start"] if i + 1 < len(segments) else total
        slot = max(0.2, next_start - seg["start"] - GAP)
        tempo = 1.0
        if raw_dur > slot:
            tempo = min(MAX_TEMPO, raw_dur / slot)
            await ffmpeg.change_tempo(raw, fitted, tempo)
            raw.unlink(missing_ok=True)
        else:
            raw.replace(fitted)
        dur = ffmpeg.wav_duration(fitted)
        seg.update(fitted=str(fitted), tempo=round(tempo, 3), dub_seconds=round(dur, 3), slot=round(slot, 3),
                   overrun=round(max(0.0, dur - slot), 3))

    # ------------------------------------------------------------------ QA
    async def qa(self, segments: list[dict], output: Path, source_duration: float) -> dict:
        n = max(1, len(segments))
        issues: list[str] = []
        overruns = [i for i, s in enumerate(segments) if s.get("overrun", 0) > OVERRUN_TOLERANCE]
        rushed = [i for i, s in enumerate(segments) if s.get("tempo", 1.0) >= MAX_TEMPO - 1e-6]
        def _untranslated(s: dict) -> bool:
            if s.get("edited"):
                return False  # a human decided (an empty line is an intentional silence)
            t = (s.get("translation") or "").strip()
            if not t:
                return True
            # identical text is fine for short lines / names ("Okay.", "Max!"), suspicious for real sentences
            return t.lower() == s["text"].strip().lower() and len(t.split()) > 2

        untranslated = [i for i, s in enumerate(segments) if _untranslated(s)]
        for i in overruns:
            issues.append(f"line {i + 1}: dub runs {segments[i]['overrun']:.2f}s into the next line")
        for i in untranslated:
            issues.append(f"line {i + 1}: missing or untranslated text")
        timing_score = round(1 - len(overruns) / n, 3)
        translation_score = round(1 - len(untranslated) / n, 3)

        out_info = await ffmpeg.media_info(output)
        duration_ok = abs(out_info["duration"] - source_duration) <= 1.0
        if not duration_ok:
            issues.append(f"output length {out_info['duration']:.1f}s differs from source {source_duration:.1f}s")
        try:
            volume = await ffmpeg.mean_volume_db(output)
        except ffmpeg.MediaError:
            volume = -91.0
        audio_ok = volume > -40.0
        if not audio_ok:
            issues.append(f"dubbed audio is too quiet ({volume:.1f} dB mean)")
        audio_score = 1.0 if audio_ok and duration_ok else 0.3
        scores = [timing_score, translation_score, audio_score]
        return {
            "timing_score": timing_score,
            "translation_accuracy_score": translation_score,
            "audio_quality_score": audio_score,
            "lip_sync_score": None,
            "lip_sync": self.p.lipsync.name,
            "lines": len(segments),
            "lines_flagged": sorted(set(overruns + untranslated)),
            "lines_speed_adjusted": sum(1 for s in segments if s.get("tempo", 1.0) > 1.0),
            "lines_at_max_speed": rushed,
            "mean_volume_db": volume,
            "quality_score": round(sum(scores) / len(scores), 3),
            "overall_pass": timing_score >= 0.9 and translation_score >= 0.95 and audio_ok and duration_ok,
            "issues": issues[:200],
        }


def _public_error(e: Exception) -> str:
    """Error text stored on the job (visible to the customer): no stack traces, no secrets, bounded."""
    if isinstance(e, (ProviderError, ffmpeg.MediaError)):
        return str(e)[:500]
    return f"Internal processing error ({e.__class__.__name__}). Please retry."



def is_running(job_id) -> bool:
    return UUID(str(job_id)) in _running
