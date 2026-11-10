from apps.services.interfaces.translation import TranslationService
import asyncio

class FakeTranslationService(TranslationService):
    async def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        await asyncio.sleep(0.1)
        return "Fake translated text"
