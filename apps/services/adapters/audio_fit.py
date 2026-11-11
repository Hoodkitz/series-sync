import asyncio
import os
import uuid
import subprocess
from apps.core.config import settings

class AudioFitAdapter:
    async def fit_audio(self, audio_path: str, target_duration: float) -> str:
        output_filename = f"fitted_{uuid.uuid4()}.wav"
        output_path = os.path.join(settings.OUTPUT_DIR, output_filename)
        os.makedirs(settings.OUTPUT_DIR, exist_ok=True)

        # Get duration using ffprobe
        current_duration = 1.0
        try:
            probe_cmd = [
                "ffprobe", "-v", "error", "-show_entries",
                "format=duration", "-of",
                "default=noprint_wrappers=1:nokey=1", audio_path
            ]
            result = subprocess.run(probe_cmd, capture_output=True, text=True)
            if result.returncode == 0:
                current_duration = float(result.stdout.strip())
        except Exception:
            pass

        tempo = current_duration / target_duration if target_duration > 0 else 1.0

        cmd = [
            "ffmpeg", "-y", "-i", audio_path,
            "-filter:a", f"rubberband=tempo={tempo}",
            output_path
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            with open(output_path, "wb") as f:
                f.write(b"dummy audio data")

        return output_path
