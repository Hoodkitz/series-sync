from apps.services.interfaces.qa import QAService
from typing import Dict
import asyncio

class FakeQAService(QAService):
    async def validate(self, video_path: str, expected_text: str) -> Dict:
        await asyncio.sleep(0.1)
        return {
            "lip_sync_score": 0.95,
            "audio_quality_score": 0.92,
            "translation_accuracy_score": 0.98,
            "overall_pass": True,
            "issues": []
        }
