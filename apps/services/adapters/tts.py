import os
import aiofiles
import uuid
from apps.services.interfaces.tts import TTSService
from apps.db.models import VoiceProfile, SyncJob
from apps.core.config import settings

class TTSAdapter(TTSService):
    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def synthesize(self, text: str, voice_profile_id: str) -> str:
        async with self.session_factory() as session:
            voice = await session.get(VoiceProfile, voice_profile_id)
            if not voice:
                raise ValueError("Voice profile not found")
            if not voice.consent:
                raise ValueError("Voice profile lacks documented consent for synthesis")

            # The job rights check is typically done in the pipeline level,
            # but we've verified consent here as strictly required.

        # For ElevenLabs or Coqui, here we would make the actual call
        # As a stub:
        output_filename = f"tts_{uuid.uuid4()}.wav"
        output_path = os.path.join(settings.OUTPUT_DIR, output_filename)

        os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
        async with aiofiles.open(output_path, "wb") as f:
            await f.write(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80\xbb\x00\x00\x00\xee\x02\x00\x02\x00\x10\x00data\x00\x00\x00\x00")

        return output_path
