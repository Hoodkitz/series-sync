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

class DubbingPipeline:
    def __init__(self, asr: ASRService, translator: TranslationService, tts: TTSService, lipsync: LipSyncService, qa: QAService, session_factory):
        self.asr = asr
        self.translator = translator
        self.tts = tts
        self.lipsync = lipsync
        self.qa = qa
        self.session_factory = session_factory

    async def run_pipeline(self, job_id: UUID, voice_profile_id: UUID):
        async with self.session_factory() as session:
            job = await session.get(SyncJob, job_id)
            if not job:
                raise ValueError("Job not found")
            
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
                job.status = JobStatus.TRANSCRIPTION.value
                await session.commit()
                transcription = await self.asr.transcribe(job.source_video_url)
                job.transcription = transcription

                # 2. Translation
                job.status = JobStatus.TRANSLATION.value
                await session.commit()
                translation = await self.translator.translate(
                    transcription, job.source_language, job.target_language
                )
                job.translation = translation

                # 3. TTS
                job.status = JobStatus.TTS_GENERATION.value
                await session.commit()
                tts_audio = await self.tts.synthesize(translation, str(voice.id))
                job.tts_audio = tts_audio

                # 4. Lip Sync
                job.status = JobStatus.LIP_SYNC.value
                await session.commit()
                # Adding AI label to metadata in a real implementation using FFmpeg
                final_video = await self.lipsync.sync_lips(job.source_video_url, tts_audio)
                job.final_video = final_video
                job.output_video_url = final_video

                # 5. QA
                job.status = JobStatus.QA_VALIDATION.value
                await session.commit()
                qa_report = await self.qa.validate(final_video, translation)
                job.qa_report = qa_report
                job.quality_score = (qa_report["lip_sync_score"] + qa_report["audio_quality_score"] + qa_report["translation_accuracy_score"]) / 3

                # Complete
                job.status = JobStatus.COMPLETED.value
                job.completed_at = datetime.utcnow()
                await session.commit()

            except Exception as e:
                job.status = JobStatus.FAILED.value
                job.errors = job.errors + [str(e)] if job.errors else [str(e)]
                await session.commit()
