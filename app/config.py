"""Centralised config via pydantic-settings, loaded from .env."""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_origins(v: str) -> list[str]:
    """Parse CORS_ORIGINS from comma-separated string to list."""
    return [o.strip() for o in v.split(",") if o.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── App ──────────────────────────────────
    CORS_ORIGINS: str = "http://localhost:5173"

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
    CLERK_JWKS_URL: str = ""
    CLERK_ISSUER: str = ""

    # ── LLM ──────────────────────────────────
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.deepseek.com/v1"
    LLM_MODEL: str = "deepseek-chat"

    # ── Embeddings / RAG ─────────────────────
    EMBEDDINGS_ENABLED: bool = False
    EMBEDDINGS_ASYNC_ENABLED: bool = True
    EMBEDDING_MODEL: str = "BAAI/bge-base-en-v1.5"
    EMBEDDING_DIMENSIONS: int = 768
    EMBEDDING_BATCH_SIZE: int = 16
    EMBEDDING_THREADS: int | None = None
    EMBEDDING_CACHE_DIR: str = ""
    RESUME_CHUNK_MAX_CHARS: int = 1800

    # ── Background jobs / SQS ────────────────
    CELERY_BROKER_URL: str = "sqs://"
    CELERY_TASK_DEFAULT_QUEUE: str = "midas-celery"
    SQS_QUEUE_URL: str = ""
    SQS_VISIBILITY_TIMEOUT: int = 3600
    SQS_WAIT_TIME_SECONDS: int = 20
    SQS_POLLING_INTERVAL: int = 1

    @property
    def celery_broker_url(self) -> str:
        return self.CELERY_BROKER_URL or "sqs://"

    @property
    def celery_broker_transport_options(self) -> dict:
        options = {
            "region": self.AWS_REGION,
            "visibility_timeout": self.SQS_VISIBILITY_TIMEOUT,
            "wait_time_seconds": self.SQS_WAIT_TIME_SECONDS,
            "polling_interval": self.SQS_POLLING_INTERVAL,
        }
        if self.SQS_QUEUE_URL:
            options["predefined_queues"] = {
                self.CELERY_TASK_DEFAULT_QUEUE: {
                    "url": self.SQS_QUEUE_URL,
                },
            }
        return options


settings = Settings()
