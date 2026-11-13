"""Core configuration."""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/seriessync")
    ENV: str = os.getenv("ENV", "production")  # fail closed
    JWT_SECRET: str = os.getenv("JWT_SECRET", "dev-secret-change-me")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "*")
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
    DEEP_LINGUISTIC_API_KEY: str = os.getenv("DEEP_LINGUISTIC_API_KEY", "")
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "base")
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    ASR_MODEL: str = os.getenv("ASR_MODEL", "whisper-1")
    ELEVENLABS_MODEL: str = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
    TTS_DEFAULT_VOICE: str = os.getenv("TTS_DEFAULT_VOICE", "pNInz6obpgDQGcFmaJgB")  # ElevenLabs stock voice
    TTS_CONCURRENCY: int = int(os.getenv("TTS_CONCURRENCY", "4"))
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_API_KEY_FILE: str = os.getenv("GEMINI_API_KEY_FILE", "~/.secrets/gemini_api_key")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    GEMINI_TTS_MODEL: str = os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
    GEMINI_TTS_VOICE: str = os.getenv("GEMINI_TTS_VOICE", "Kore")
    # When PROVIDER_MODE=gemini and tests or local development should not call the real API,
    # set GEMINI_MOCK_TTS_LIMIT to a positive integer to simulate the free-tier daily TTS limit.
    # 0 = unlimited (default).
    GEMINI_MOCK_TTS_LIMIT: int = int(os.getenv("GEMINI_MOCK_TTS_LIMIT", "0"))
    # fake = deterministic local providers (dev/tests); real = OpenAI-compatible ASR/LLM + ElevenLabs;
    # gemini = one Google key for transcription, translation and speech (no voice cloning)
    PROVIDER_MODE: str = os.getenv("PROVIDER_MODE", "real")
    STORAGE_DIR: str = os.getenv("STORAGE_DIR", "./var/storage")
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "4096"))
    MAX_DURATION_MINUTES: int = int(os.getenv("MAX_DURATION_MINUTES", "90"))
    BACKGROUND_VOLUME: float = float(os.getenv("BACKGROUND_VOLUME", "0.18"))

    class Config:
        env_file = ".env"


settings = Settings()
if settings.ENV != "development" and (settings.JWT_SECRET == "dev-secret-change-me" or len(settings.JWT_SECRET) < 32):
    raise RuntimeError("JWT_SECRET must be set (>= 32 chars) outside development")
if settings.ENV != "development" and settings.PROVIDER_MODE == "fake":
    raise RuntimeError("PROVIDER_MODE=fake is only allowed with ENV=development")
if settings.PROVIDER_MODE not in ("fake", "real", "gemini"):
    raise RuntimeError("PROVIDER_MODE must be fake, real or gemini")
if settings.PROVIDER_MODE == "real" and settings.ENV != "development" and not (
        settings.OPENAI_API_KEY and settings.ELEVENLABS_API_KEY):
    raise RuntimeError("OPENAI_API_KEY and ELEVENLABS_API_KEY are required for PROVIDER_MODE=real")
