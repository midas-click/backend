"""Resume model — stores metadata, raw+structured text, and S3 keys."""

from datetime import datetime
from typing import List, Optional

from beanie import Document
from pydantic import BaseModel, Field

from app.models.base import MidasDocument


class ResumeSection(BaseModel):
    title: str          # e.g. "Experience", "Education"
    content: str


class ResumeDocument(Document, MidasDocument):
    """Each uploaded or tailored resume version."""

    user_id: str = Field(default="default")       # Clerk user ID (sub claim)
    team_id: str = Field(default="default")       # Clerk organization ID (org_id claim)
    profile_id: Optional[str] = None              # active profile ID
    original_filename: str
    s3_key: str
    s3_url: Optional[str] = None

    raw_text: Optional[str] = None          # full extracted text
    sections: List[ResumeSection] = Field(default_factory=list)

    tags: List[str] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "resumes"
        indexes = [
            "user_id",
            "team_id",
            "profile_id",
            ("team_id", "profile_id"),
        ]
