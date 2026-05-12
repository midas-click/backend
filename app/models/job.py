"""Job model — manually entered jobs or bookmarked listings."""

from datetime import datetime
from typing import List, Optional

from beanie import Document
from pydantic import BaseModel, Field

from app.models.base import MidasDocument


class JobDocument(Document, MidasDocument):

    user_id: str = Field(default="default")       # Clerk user ID (sub claim)
    org_id: str = Field(default="default")        # Clerk organization ID

    title: str
    company: str
    description: Optional[str] = None
    location: Optional[str] = None
    remote: Optional[bool] = None
    salary_range: Optional[str] = None

    source_url: Optional[str] = None
    source_name: str = "manual"  # manual | linkedin | indeed | greenhouse | ...


    tags: List[str] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "jobs"
        indexes = [
            "user_id",
            "org_id",
            "company",
        ]


class JobCreate(BaseModel):
    title: str
    company: str
    description: Optional[str] = None
    location: Optional[str] = None
    remote: Optional[bool] = None
    salary_range: Optional[str] = None
    source_url: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class JobAnalyzeRequest(BaseModel):
    raw_text: str
    source_url: str = ""


class JobUpdate(BaseModel):
    title: Optional[str] = None
    company: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    remote: Optional[bool] = None
    salary_range: Optional[str] = None
    source_url: Optional[str] = None
    tags: Optional[List[str]] = None
