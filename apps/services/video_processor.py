"""Video processing service for Series Sync."""
import asyncio
import subprocess
import tempfile
import os
from pathlib import Path
from typing import Optional
from apps.core.config import settings


class VideoProcessor:
    def __init__(self):
        self._ffmpeg_path = "ffmpeg"
        self._ffprobe_path = "ffprobe"
        self._tmpdir = Path(tempfile.mkdtemp(prefix="seriessync_"))

    async def get_video_info(self, video_url: str) -> dict:
        """Get video metadata using FFprobe."""
        cmd = [
            self._ffprobe_path, "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", video_url
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            import json
            return json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            raise ValueError(f"FFprobe failed: {e.stderr}")

    async def extract_audio(self, video_url: str, output_path: str) -> str:
        """Extract audio from video."""
        cmd = [
            self._ffmpeg_path, "-y", "-i", video_url,
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            output_path
        ]
        subprocess.run(cmd, check=True)
        return output_path

    async def split_audio_by_speaker(self, audio_path: str, output_dir: str, num_speakers: int = 2) -> List[str]:
        """Split audio by speaker (stub)."""
        # In production: use pyannote.audio or similar for speaker diarization
        parts = []
        for i in range(num_speakers):
            part_path = os.path.join(output_dir, f"speaker_{i}.wav")
            parts.append(part_path)
        return parts

    async def export_video(self, video_path: str, output_path: str) -> str:
        """Export final video."""
        cmd = [
            self._ffmpeg_path, "-y", "-i", video_path, output_path
        ]
        subprocess.run(cmd, check=True)
        return output_path


class PipelineService:
    """High-level pipeline service."""
    def __init__(self):
        self.video = VideoProcessor()
        self.pipeline = DubbingPipeline()

    async def process_upload(self, tenant_id: str, source_url: str, source_lang: str = "en", target_lang: str = "de") -> SyncJob:
        """Full pipeline: upload → transcript → translate → TTS → lip-sync → QA."""
        # Step 1: Get video info
        video_info = await self.video.get_video_info(source_url)
        
        # Step 2: Create job
        job = await self.pipeline.create_job(tenant_id, source_url, source_lang, target_lang)
        
        # Step 3: Advance through stages (stub, replace with real pipeline)
        await self.pipeline.advance_stage(job.id, JobStatus.PREPROCESSING)
        await self.pipeline.advance_stage(job.id, JobStatus.AUDIO_SEPARATION)
        await self.pipeline.advance_stage(job.id, JobStatus.DIARIZATION)
        await self.pipeline.advance_stage(job.id, JobStatus.TRANSCRIPTION)
        await self.pipeline.advance_stage(job.id, JobStatus.TRANSLATION)
        await self.pipeline.advance_stage(job.id, JobStatus.TTS_GENERATION)
        await self.pipeline.advance_stage(job.id, JobStatus.LIP_SYNC)
        await self.pipeline.advance_stage(job.id, JobStatus.QA_VALIDATION)
        await self.pipeline.advance_stage(job.id, JobStatus.RENDERING)
        
        # Complete
        output_url = f"https://storage.example.com/sync/{job.id}/output.mp4"
        await self.pipeline.complete_job(job.id, output_url)
        
        return job
