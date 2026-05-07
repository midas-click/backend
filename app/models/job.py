"""Job model — manually entered jobs or bookmarked listings."""

from datetime import datetime
from typing import List, Optional

from beanie import Document
from pydantic import BaseModel, Field

from app.models.base import MidasDocument


class JobDocument(Document, MidasDocument):

    user_id: str = Field(default="default")

    title: str
    company: str
    description: Optional[str] = None
    location: Optional[str] = None
    remote: Optional[bool] = None
    salary_range: Optional[str] = None

    source_url: Optional[str] = None
    source_name: str = "manual"  # manual | linkedin | indeed | greenhouse | ...

    status: str = "saved"  # saved | applied | archived

    extracted_keywords: List[str] = Field(default_factory=list)

    tags: List[str] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "jobs"
        indexes = ["user_id", "status", "company"]


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


class JobImportURL(BaseModel):
    url: str


class JobUpdate(BaseModel):
    title: Optional[str] = None
    company: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    remote: Optional[bool] = None
    salary_range: Optional[str] = None
    source_url: Optional[str] = None
    status: Optional[str] = None
    extracted_keywords: Optional[List[str]] = None
    tags: Optional[List[str]] = None
