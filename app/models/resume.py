"""Resume model — stores metadata, raw+structured text, and S3 keys."""

from datetime import UTC, datetime

from beanie import Document
from pydantic import BaseModel, Field

from app.models.base import MidasDocument


class ResumeSection(BaseModel):
    title: str          # e.g. "Experience", "Education"
    content: str


class ResumeDocument(Document, MidasDocument):
    """Each uploaded resume version."""

    user_id: str = Field(default="default")       # Clerk user ID (sub claim)
    org_id: str = Field(default="default")       # Clerk organization ID (org_id claim)
    profile_id: str | None = None              # active profile ID
    original_filename: str
    s3_key: str
    s3_url: str | None = None

    raw_text: str | None = None          # full extracted text
    sections: list[ResumeSection] = Field(default_factory=list)

    tags: list[str] = Field(default_factory=list)

    embedding_status: str = Field(default="disabled")
    embedding_error: str | None = None
    embedded_at: datetime | None = None
    vector_store: str | None = None
    vector_chunk_count: int = 0

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "resumes"
        indexes = [
            "user_id",
            "org_id",
            "profile_id",
            ("org_id", "profile_id"),
        ]
