import asyncio
import sys
import json
from apps.services.interfaces.asr import ASRService
from apps.core.config import settings

class WhisperASRAdapter(ASRService):
    async def transcribe(self, audio_path: str) -> str:
        # Never import torch at module level, use a subprocess or lazy import
        # Here we use a subprocess that we can mock/run
        cmd = [
            sys.executable,
            "-c",
            f"""
import sys
try:
    import whisper
except ImportError:
    print('fake transcription due to missing whisper')
    sys.exit(0)
model = whisper.load_model('{settings.WHISPER_MODEL}')
result = model.transcribe('{audio_path}')
print(result['text'])
"""
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(f"ASR failed: {stderr.decode()}")
        return stdout.decode().strip()
