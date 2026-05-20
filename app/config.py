"""Centralised config via pydantic-settings, loaded from .env."""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_origins(v: str) -> list[str]:
    """Parse CORS_ORIGINS from comma-separated string to list."""
    return [o.strip() for o in v.split(",") if o.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── App ──────────────────────────────────
    APP_ENV: str = "development"
    DEBUG: bool = True
    CORS_ORIGINS: str = "http://localhost:5173"

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value: object) -> object:
        if isinstance(value, str) and value.lower() in {"release", "prod", "production"}:
            return False
        return value

    @field_validator("EMBEDDING_THREADS", mode="before")
    @classmethod
    def parse_optional_int(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @property
    def cors_origins_list(self) -> list[str]:
        return _parse_origins(self.CORS_ORIGINS)

    # ── MongoDB ──────────────────────────────
    MONGODB_URI: str = "mongodb+srv://db_user:db_pass@db_name.o3bprl5.mongodb.net/?appName=midas"
    MONGO_DB_NAME: str = ""

    # ── AWS S3 ───────────────────────────────
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str = "midas-click-resumes"

    # ── Clerk Auth ────────────────────────────
    CLERK_SECRET_KEY: str = ""
    CLERK_PUBLISHABLE_KEY: str = ""
    CLERK_JWKS_URL: str = ""
    CLERK_ISSUER: str = ""

    # ── LLM ──────────────────────────────────
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.deepseek.com/v1"
    LLM_MODEL: str = "deepseek-chat"

    # ── Embeddings / RAG ─────────────────────
    EMBEDDING_MODEL: str = "BAAI/bge-base-en-v1.5"
    EMBEDDING_DIMENSIONS: int = 768
    EMBEDDING_BATCH_SIZE: int = 16
    EMBEDDING_THREADS: int | None = None
    EMBEDDING_CACHE_DIR: str = ""
    RESUME_CHUNK_MAX_CHARS: int = 1800


settings = Settings()
