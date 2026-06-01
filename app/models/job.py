"""Job model — manually entered jobs or bookmarked listings."""

from datetime import UTC, datetime

from beanie import Document
from pydantic import BaseModel, Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.models.base import MidasDocument


class JobDocument(Document, MidasDocument):

    user_id: str = Field(default="default")       # Clerk user ID (sub claim)
    org_id: str = Field(default="default")        # Clerk organization ID

    title: str
    company: str
    location: str | None = None
    remote: bool | None = None
    salary_range: str | None = None

    source_url: str | None = None
    org_name: str = "Unknown"     # denormalized org name for display


    tags: list[str] = Field(default_factory=list)

    embedding_status: str = Field(default="disabled")
    embedding_error: str | None = None
    embedded_at: datetime | None = None
    vector_store: str | None = None
    vector_chunk_count: int = 0

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "jobs"
        indexes = [
            IndexModel(
                [("created_at", DESCENDING), ("_id", DESCENDING)],
                name="jobs_created_cursor",
            ),
            IndexModel(
                [("user_id", ASCENDING), ("created_at", DESCENDING), ("_id", DESCENDING)],
                name="jobs_user_created_cursor",
            ),
            IndexModel(
                [("org_id", ASCENDING), ("created_at", DESCENDING), ("_id", DESCENDING)],
                name="jobs_org_created_cursor",
            ),
            IndexModel(
                [("source_url", ASCENDING)],
                unique=True,
                partialFilterExpression={"source_url": {"$type": "string"}},
                name="unique_source_url",
            ),
        ]


class JobAnalyzeRequest(BaseModel):
    raw_text: str
    source_url: str = ""


class JobListItem(BaseModel):
    id: str
    user_id: str
    org_id: str | None = None
    title: str
    company: str
    location: str | None = None
    remote: bool | None = None
    salary_range: str | None = None
    source_url: str | None = None
    org_name: str
    tags: list[str] = Field(default_factory=list)
    embedding_status: str | None = None
    embedding_error: str | None = None
    embedded_at: datetime | None = None
    vector_store: str | None = None
    vector_chunk_count: int = 0
    created_at: datetime
