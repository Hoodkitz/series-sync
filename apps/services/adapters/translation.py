import json
import os
import aiohttp
from apps.services.interfaces.translation import TranslationService

class LLMTranslationAdapter(TranslationService):
    async def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        api_key = os.getenv("OPENAI_API_KEY", "")
        model = os.getenv("LLM_MODEL", "gpt-3.5-turbo")

        prompt = (
            f"Translate the following text from {source_lang} to {target_lang}. "
            "Strictly preserve all slang, jokes, and cultural nuances so that the dubbing sounds natural.\n\n"
            f"Text:\n{text}"
        )

        # If no key, we act as a mock for tests when networking is disabled
        if not api_key:
            return f"[Translated to {target_lang}]: {text}"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are an expert movie translation AI."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(f"{base_url}/chat/completions", headers=headers, json=data) as resp:
                resp.raise_for_status()
                result = await resp.json()
                return result["choices"][0]["message"]["content"].strip()
