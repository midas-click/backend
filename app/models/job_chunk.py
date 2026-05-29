"""Vector-searchable job chunks derived from saved job descriptions."""

from datetime import UTC, datetime

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel

from app.models.base import MidasDocument


class JobChunkDocument(Document, MidasDocument):
    job_id: str
    user_id: str
    org_id: str
    chunk_index: int
    content: str
    embedding: list[float]
    embedding_model: str
    embedding_dimensions: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "job_chunks"
        indexes = [
            IndexModel([("job_id", ASCENDING)], name="job_chunks_job"),
            IndexModel([("org_id", ASCENDING), ("job_id", ASCENDING)], name="job_chunks_org_job"),
        ]
