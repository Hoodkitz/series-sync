"""AI provider adapters: speech recognition, translation, speech synthesis, voice cloning, lip-sync.

Real adapters talk to hosted APIs (OpenAI-compatible ASR/LLM, ElevenLabs). Fakes produce deterministic, real media
files so the whole pipeline (ffmpeg timing, mixing, muxing, QA) runs end-to-end in tests without network access.
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx

from apps.core.config import settings
from apps.media import ffmpeg


class ProviderError(RuntimeError):
    """A provider call failed in a way that retrying the job later may fix."""


@dataclass
class Transcript:
    language: str
    segments: list[dict]  # {"start": float, "end": float, "text": str}


class ASR(Protocol):
    async def transcribe(self, audio_path: Path, language: str | None) -> Transcript: ...


class Translator(Protocol):
    async def translate(self, segments: list[dict], source: str, target: str) -> list[str]: ...


class TTS(Protocol):
    async def synthesize(self, text: str, voice_id: str, language: str, out_path: Path) -> Path: ...


class VoiceCloner(Protocol):
    async def clone(self, name: str, sample: Path) -> str: ...

    async def delete(self, voice_id: str) -> None: ...


class LipSync(Protocol):
    name: str

    async def apply(self, video: Path, audio: Path, out_path: Path) -> Path: ...


# ---------------------------------------------------------------- shared HTTP helper
async def _post(url: str, *, headers: dict, retries: int = 3, timeout: float = 300, **kw) -> httpx.Response:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as c:
                r = await c.post(url, headers=headers, **kw)
            if r.status_code in (429, 500, 502, 503, 504):
                last = ProviderError(f"{url} -> HTTP {r.status_code}")
                await asyncio.sleep(2 ** attempt)
                continue
            if r.status_code >= 400:
                raise ProviderError(f"{url.split('?')[0]} -> HTTP {r.status_code}: {r.text[:200]}")
            return r
        except httpx.HTTPError as e:
            last = ProviderError(f"{url.split('?')[0]} unreachable: {e.__class__.__name__}")
            await asyncio.sleep(2 ** attempt)
    raise last or ProviderError("request failed")


# ---------------------------------------------------------------- OpenAI-compatible ASR
class OpenAIWhisperASR:
    """Hosted Whisper with segment timestamps. Long files are cut into chunks below the 25 MB upload limit."""

    CHUNK_SECONDS = 20 * 60

    async def transcribe(self, audio_path: Path, language: str | None) -> Transcript:
        info = await ffmpeg.media_info(audio_path)
        total = info["duration"]
        segments: list[dict] = []
        detected = language or ""
        start = 0.0
        idx = 0
        while start < total or (idx == 0 and total == 0):
            chunk = audio_path
            if total > self.CHUNK_SECONDS:
                chunk = audio_path.with_name(f"asr_chunk_{idx}.mp3")
                await ffmpeg.cut_audio(audio_path, chunk, start, self.CHUNK_SECONDS)
            data = {"model": settings.ASR_MODEL, "response_format": "verbose_json",
                    "timestamp_granularities[]": "segment"}
            if language:
                data["language"] = language
            audio = chunk.read_bytes()  # bytes, not a file handle: retries must resend the full file
            r = await _post(f"{settings.OPENAI_BASE_URL}/audio/transcriptions",
                            headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                            data=data, files={"file": (chunk.name, audio, "audio/mpeg")})
            body = r.json()
            detected = detected or _lang_code(body.get("language", ""))
            for s in body.get("segments", []):
                text = (s.get("text") or "").strip()
                if text:
                    segments.append({"start": round(start + float(s["start"]), 3),
                                     "end": round(start + float(s["end"]), 3), "text": text})
            idx += 1
            start += self.CHUNK_SECONDS
            if total <= self.CHUNK_SECONDS:
                break
        return Transcript(language=detected or "en", segments=segments)


_LANG_NAMES = {"english": "en", "german": "de", "french": "fr", "spanish": "es", "italian": "it",
               "portuguese": "pt", "dutch": "nl", "polish": "pl", "turkish": "tr", "russian": "ru",
               "japanese": "ja", "korean": "ko", "chinese": "zh"}


def _lang_code(name: str) -> str:
    name = (name or "").strip().lower()
    return name if len(name) == 2 else _LANG_NAMES.get(name, "")


# ---------------------------------------------------------------- LLM translation tuned for dubbing
DUB_PROMPT = """You are a professional dubbing translator. Translate each line from {src} to {tgt} for lip-synchronous
dubbing of a TV series. Rules:
- Keep meaning, tone, register, slang, jokes and cultural references; adapt idioms naturally, never literally.
- Each line will be spoken in the given number of seconds. Keep the translation speakable in that time
  (roughly {cps} characters per second); shorten wording rather than exceed it.
- Keep names, numbers and on-screen terms consistent across lines.
- Return JSON only: {{"lines": ["...", "..."]}} with exactly one entry per input line, same order."""


class LLMTranslator:
    BATCH = 30

    async def translate(self, segments: list[dict], source: str, target: str) -> list[str]:
        out: list[str] = []
        for i in range(0, len(segments), self.BATCH):
            batch = segments[i:i + self.BATCH]
            out.extend(await self._batch(batch, source, target, context=out[-3:]))
        return out

    async def _batch(self, batch: list[dict], source: str, target: str, context: list[str]) -> list[str]:
        lines = [{"i": n, "seconds": round(s["end"] - s["start"], 2), "text": s["text"]} for n, s in enumerate(batch)]
        user = json.dumps({"previous_translated_lines": context, "lines": lines}, ensure_ascii=False)
        for attempt in range(2):
            r = await _post(f"{settings.OPENAI_BASE_URL}/chat/completions",
                            headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                            json={"model": settings.LLM_MODEL, "temperature": 0.3,
                                  "response_format": {"type": "json_object"},
                                  "messages": [{"role": "system",
                                                "content": DUB_PROMPT.format(src=source, tgt=target, cps=15)},
                                               {"role": "user", "content": user}]})
            try:
                content = r.json()["choices"][0]["message"]["content"]
                result = json.loads(content)["lines"]
                if isinstance(result, list) and len(result) == len(batch):
                    return [str(x).strip() for x in result]
            except (KeyError, IndexError, ValueError, TypeError):
                pass
        raise ProviderError("translation model returned a malformed or incomplete response")


# ---------------------------------------------------------------- ElevenLabs TTS + voice cloning
class ElevenLabsTTS:
    BASE = "https://api.elevenlabs.io/v1"

    async def synthesize(self, text: str, voice_id: str, language: str, out_path: Path) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9]{8,64}", voice_id or ""):
            raise ProviderError("invalid ElevenLabs voice id")
        r = await _post(f"{self.BASE}/text-to-speech/{voice_id}?output_format=mp3_44100_128",
                        headers={"xi-api-key": settings.ELEVENLABS_API_KEY, "accept": "audio/mpeg"},
                        json={"text": text, "model_id": settings.ELEVENLABS_MODEL,
                              "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "style": 0.3}})
        mp3 = out_path.with_suffix(".mp3")
        mp3.write_bytes(r.content)
        await ffmpeg.to_wav(mp3, out_path)
        mp3.unlink(missing_ok=True)
        return out_path


class ElevenLabsCloner:
    async def clone(self, name: str, sample: Path) -> str:
        r = await _post(f"{ElevenLabsTTS.BASE}/voices/add", headers={"xi-api-key": settings.ELEVENLABS_API_KEY},
                        data={"name": name[:100], "remove_background_noise": "true"},
                        files={"files": (sample.name, sample.read_bytes(), "application/octet-stream")})
        voice_id = r.json().get("voice_id")
        if not voice_id:
            raise ProviderError("voice cloning returned no voice id")
        return voice_id

    async def delete(self, voice_id: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9]{8,64}", voice_id or ""):
            return
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.delete(f"{ElevenLabsTTS.BASE}/voices/{voice_id}",
                                   headers={"xi-api-key": settings.ELEVENLABS_API_KEY})
        except httpx.HTTPError as e:
            raise ProviderError(f"voice deletion failed: {e.__class__.__name__}")
        if r.status_code >= 400 and r.status_code != 404:
            raise ProviderError(f"voice deletion failed: HTTP {r.status_code}")


class NoLipSync:
    """Audio-only dub (default). Lip-sync needs a GPU model or a hosted lip-sync API."""
    name = "none"

    async def apply(self, video: Path, audio: Path, out_path: Path) -> Path:
        return video


# ---------------------------------------------------------------- fakes (tests / local demo)
class FakeASR:
    async def transcribe(self, audio_path: Path, language: str | None) -> Transcript:
        info = await ffmpeg.media_info(audio_path)
        dur = max(info["duration"], 1.0)
        segs, t, n = [], 0.3, 1
        while t + 1.2 < dur:
            end = min(dur - 0.1, t + 1.6)
            segs.append({"start": round(t, 3), "end": round(end, 3), "text": f"Line {n}, you know what I mean?"})
            t, n = end + 0.4, n + 1
        return Transcript(language=language or "en", segments=segs)


class FakeTranslator:
    async def translate(self, segments: list[dict], source: str, target: str) -> list[str]:
        return [f"Zeile {i + 1}, weißt du, was ich meine?" for i, _ in enumerate(segments)]


class FakeTTS:
    """Writes a tone whose length follows the text length (~14 chars/second), like real speech would."""

    async def synthesize(self, text: str, voice_id: str, language: str, out_path: Path) -> Path:
        return await ffmpeg.synth_tone(out_path, max(0.3, len(text) / 14.0))


class FakeCloner:
    async def clone(self, name: str, sample: Path) -> str:
        return "fakevoice" + str(abs(hash(name)) % 10**8)

    async def delete(self, voice_id: str) -> None:
        self.deleted = getattr(self, "deleted", []) + [voice_id]


@dataclass
class Providers:
    asr: ASR
    translator: Translator
    tts: TTS
    lipsync: LipSync
    cloner: VoiceCloner


def default_providers() -> Providers:
    if settings.PROVIDER_MODE == "fake":
        return Providers(FakeASR(), FakeTranslator(), FakeTTS(), NoLipSync(), FakeCloner())
    return Providers(OpenAIWhisperASR(), LLMTranslator(), ElevenLabsTTS(), NoLipSync(), ElevenLabsCloner())
