"""Vector-searchable resume chunks derived from parsed resume sections."""

from datetime import UTC, datetime

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel

from app.models.base import MidasDocument


class ResumeChunkDocument(Document, MidasDocument):
    resume_id: str
    user_id: str
    org_id: str
    profile_id: str | None = None
    section_title: str
    chunk_index: int
    content: str
    embedding: list[float]
    embedding_model: str
    embedding_dimensions: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "resume_chunks"
        indexes = [
            IndexModel([("resume_id", ASCENDING)], name="resume_chunks_resume"),
            IndexModel(
                [("org_id", ASCENDING), ("profile_id", ASCENDING)],
                name="resume_chunks_org_profile",
            ),
            IndexModel(
                [("org_id", ASCENDING), ("profile_id", ASCENDING), ("resume_id", ASCENDING)],
                name="resume_chunks_org_profile_resume",
            ),
        ]
