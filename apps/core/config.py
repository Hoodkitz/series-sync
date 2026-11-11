"""Core configuration."""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/seriessync")
    ENV: str = os.getenv("ENV", "development")
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
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-3.5-turbo")
    OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "/tmp/series-sync")
    CHECKPOINT_DIR: str = os.getenv("CHECKPOINT_DIR", "/tmp/checkpoints")

    class Config:
        env_file = ".env"


settings = Settings()
if settings.ENV != "development" and (settings.JWT_SECRET == "dev-secret-change-me" or len(settings.JWT_SECRET) < 32):
    raise RuntimeError("JWT_SECRET must be set (>= 32 chars) outside development")
