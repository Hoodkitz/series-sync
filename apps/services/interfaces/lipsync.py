from abc import ABC, abstractmethod

class LipSyncService(ABC):
    @abstractmethod
    async def sync_lips(self, video_path: str, audio_path: str) -> str:
        pass
