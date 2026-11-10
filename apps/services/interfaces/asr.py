from abc import ABC, abstractmethod

class ASRService(ABC):
    @abstractmethod
    async def transcribe(self, audio_path: str) -> str:
        pass
