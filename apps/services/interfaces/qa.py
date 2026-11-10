from abc import ABC, abstractmethod
from typing import Dict

class QAService(ABC):
    @abstractmethod
    async def validate(self, video_path: str, expected_text: str) -> Dict:
        pass
