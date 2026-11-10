from apps.services.interfaces.lipsync import LipSyncService
import asyncio

class FakeLipSyncService(LipSyncService):
    async def sync_lips(self, video_path: str, audio_path: str) -> str:
        await asyncio.sleep(0.1)
        return "fake_lipsync_video.mp4"
