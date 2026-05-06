"""Resume model — stores metadata, raw+structured text, and S3 keys."""

from datetime import datetime
from typing import List, Optional

from beanie import Document
from pydantic import BaseModel, Field, model_serializer


class ResumeSection(BaseModel):
    title: str          # e.g. "Experience", "Education"
    content: str


class ResumeDocument(Document):
    """Each uploaded or tailored resume version."""

    @model_serializer(mode="wrap")
    def _ser(self, serializer, info):
        data = serializer(self)
        if "_id" in data:
            data["id"] = str(data.pop("_id"))
        return data

    user_id: str = Field(default="default")
    original_filename: str
    s3_key: str
    s3_url: Optional[str] = None

    raw_text: Optional[str] = None          # full extracted text
    sections: List[ResumeSection] = Field(default_factory=list)

    parent_resume_id: Optional[str] = None  # links tailored version → source
    tailored_for_job_id: Optional[str] = None
    tailored_prompt: Optional[str] = None   # LLM prompt used
    tailored_label: Optional[str] = None    # e.g. "Backend / Python / Go"

    # Performance tracking
    total_applications: int = 0
    interview_count: int = 0
    offer_count: int = 0

    tags: List[str] = Field(default_factory=list)

    version: int = 1
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "resumes"
        indexes = [
            "user_id",
            "parent_resume_id",
            "tailored_for_job_id",
        ]
