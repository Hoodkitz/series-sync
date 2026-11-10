from abc import ABC, abstractmethod

class TTSService(ABC):
    @abstractmethod
    async def synthesize(self, text: str, voice_profile_id: str) -> str:
        pass
