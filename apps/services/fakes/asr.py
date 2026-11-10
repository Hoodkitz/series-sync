from apps.services.interfaces.asr import ASRService
import asyncio

class FakeASRService(ASRService):
    async def transcribe(self, audio_path: str) -> str:
        await asyncio.sleep(0.1)
        return "Fake transcription text"
