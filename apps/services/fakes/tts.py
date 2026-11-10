from apps.services.interfaces.tts import TTSService
import asyncio

class FakeTTSService(TTSService):
    async def synthesize(self, text: str, voice_profile_id: str) -> str:
        await asyncio.sleep(0.1)
        return "fake_tts_audio.wav"
