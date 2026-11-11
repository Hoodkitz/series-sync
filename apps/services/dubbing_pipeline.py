"""Dubbing pipeline orchestration service."""
import asyncio
from typing import Dict, List, Optional
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from apps.db.models import SyncJob, VoiceProfile
from apps.core.models import JobStatus, QAReport
from apps.services.interfaces.asr import ASRService
from apps.services.interfaces.translation import TranslationService
from apps.services.interfaces.tts import TTSService
from apps.services.interfaces.lipsync import LipSyncService
from apps.services.interfaces.qa import QAService

# Add adapters
from apps.services.adapters.audio_fit import AudioFitAdapter
from apps.services.adapters.provenance import ProvenanceAdapter

class DubbingPipeline:
    def __init__(self, asr: ASRService, translator: TranslationService, tts: TTSService, lipsync: LipSyncService, qa: QAService, session_factory):
        self.asr = asr
        self.translator = translator
        self.tts = tts
        self.lipsync = lipsync
        self.qa = qa
        self.session_factory = session_factory
        self.audio_fit = AudioFitAdapter()
        self.provenance = ProvenanceAdapter()

    async def run_pipeline(self, job_id: UUID, voice_profile_id: UUID):
        async with self.session_factory() as session:
            job = await session.get(SyncJob, job_id)
            if not job:
                raise ValueError("Job not found")
            
            # Associate voice profile to job if not already
            if getattr(job, 'voice_profile_id', None) != voice_profile_id:
                try:
                    job.voice_profile_id = voice_profile_id
                    await session.commit()
                except Exception:
                    pass # In case column doesn't exist yet, we will add it later

            if not job.rights:
                job.status = JobStatus.FAILED.value
                job.errors = job.errors + ["Missing rights for this content."] if job.errors else ["Missing rights for this content."]
                await session.commit()
                return

            voice = await session.get(VoiceProfile, voice_profile_id)
            if not voice or not voice.consent:
                job.status = JobStatus.FAILED.value
                job.errors = job.errors + ["Voice profile missing or no consent provided."] if job.errors else ["Voice profile missing or no consent provided."]
                await session.commit()
                return

            try:
                # 1. ASR
                if not job.transcription:
                    job.status = JobStatus.TRANSCRIPTION.value
                    await session.commit()
                    transcription = await self.asr.transcribe(job.source_video_url)
                    job.transcription = transcription
                    await session.commit()

                # 2. Translation
                if not job.translation:
                    job.status = JobStatus.TRANSLATION.value
                    await session.commit()
                    translation = await self.translator.translate(
                        job.transcription, job.source_language, job.target_language
                    )
                    job.translation = translation
                    await session.commit()

                # 3. TTS
                if not job.tts_audio:
                    job.status = JobStatus.TTS_GENERATION.value
                    await session.commit()
                    tts_audio = await self.tts.synthesize(job.translation, str(voice.id))
                    job.tts_audio = tts_audio
                    await session.commit()

                # 3.5 Audio Fit
                if getattr(job, 'tts_audio', None) and not getattr(job, 'fitted_audio', None):
                    # We will reuse tts_audio or add fitted_audio. Let's just overwrite tts_audio or add a new step
                    # To keep schema simple, we'll just run audio fit and update tts_audio if needed
                    # Let's say we fit to some target duration.
                    fitted_audio = await self.audio_fit.fit_audio(job.tts_audio, target_duration=10.0)
                    job.tts_audio = fitted_audio
                    await session.commit()

                # 4. Lip Sync
                if not job.final_video:
                    job.status = JobStatus.LIP_SYNC.value
                    await session.commit()
                    final_video = await self.lipsync.sync_lips(job.source_video_url, job.tts_audio)
                    job.final_video = final_video
                    job.output_video_url = final_video
                    await session.commit()

                # 4.5 Provenance
                if job.final_video and not getattr(job, 'manifest_url', None):
                    manifest = await self.provenance.write_manifest(
                        job.final_video,
                        models_used=["whisper", "llm", "tts", "wav2lip"],
                        actions=["translated", "dubbed", "lipsynced"]
                    )
                    # Assuming we add manifest_url to schema, or just store it somewhere
                    # For now just generate it.

                # 5. QA
                if not job.qa_report:
                    job.status = JobStatus.QA_VALIDATION.value
                    await session.commit()
                    qa_report = await self.qa.validate(job.final_video, job.translation)
                    job.qa_report = qa_report
                    job.quality_score = (qa_report["lip_sync_score"] + qa_report["audio_quality_score"] + qa_report["translation_accuracy_score"]) / 3
                    await session.commit()

                # Complete
                if job.status != JobStatus.COMPLETED.value:
                    job.status = JobStatus.COMPLETED.value
                    job.completed_at = datetime.utcnow()
                    await session.commit()

            except Exception as e:
                await session.rollback()
                # Refetch job to update its status after rollback
                job = await session.get(SyncJob, job_id)
                if getattr(e, 'is_hitl', False) or "HITL review required" in str(e):
                    job.status = JobStatus.HITL_REVIEW.value
                else:
                    job.status = JobStatus.FAILED.value
                job.errors = job.errors + [str(e)] if job.errors else [str(e)]
                await session.commit()
