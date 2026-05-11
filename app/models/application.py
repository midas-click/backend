"""Application model — the core ATS entity."""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from beanie import Document
from pydantic import BaseModel, Field

from app.models.base import MidasDocument


# ── Enums ────────────────────────────────────
class ApplicationStage(str, Enum):
    APPLIED = "applied"
    PHONE_SCREEN = "phone_screen"
    TECHNICAL = "technical"
    TEAM_INTERVIEW = "team_interview"
    OFFER = "offer"
    REJECTED = "rejected"


# ── Embedded sub-documents ───────────────────
class CommunicationLog(BaseModel):
    date: datetime = Field(default_factory=datetime.utcnow)
    channel: str = "email"  # email | phone | linkedin | in_person
    summary: str
    raw_content: Optional[str] = None


class TimelineEvent(BaseModel):
    date: datetime = Field(default_factory=datetime.utcnow)
    event: str  # e.g. "Applied", "Phone screen scheduled"
    detail: Optional[str] = None


# ── Main document ────────────────────────────
class ApplicationDocument(Document, MidasDocument):
    """Stores a single job application tracked through the pipeline."""

    user_id: str = Field(default="default")  # Clerk user ID (sub claim)
    team_id: str = Field(default="default")  # Clerk organization ID (org_id claim)
    profile_id: Optional[str] = None         # active profile ID
    job_id: Optional[str] = None  # links to source Job
    job_title: str
    company: str
    location: Optional[str] = None
    source_url: Optional[str] = None  # denormalized from Job — survives job deletion
    salary_expectation: Optional[str] = None

    stage: str = ApplicationStage.APPLIED.value
    initial_contact_date: Optional[datetime] = None
    resume_id: Optional[str] = None
    resume_filename: Optional[str] = None  # denormalized from Resume — survives resume deletion

    tags: List[str] = Field(default_factory=list)  # e.g. ["react", "healthtech"]

    match_score: Optional[float] = None         # 0-100
    match_explanation: Optional[str] = None

    communication_log: List[CommunicationLog] = Field(default_factory=list)
    timeline: List[TimelineEvent] = Field(default_factory=list)

    follow_up_date: Optional[datetime] = None
    notes: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "applications"
        indexes = [
            "user_id",
            "stage",
            "company",
            "tags",
            ("user_id", "stage"),
        ]


# ── API request / response schemas (Pydantic) ──
class ApplicationCreate(BaseModel):
    job_id: Optional[str] = None
    job_title: str
    company: str
    stage: Optional[str] = None
    location: Optional[str] = None
    source_url: Optional[str] = None
    salary_expectation: Optional[str] = None
    initial_contact_date: Optional[datetime] = None
    resume_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class ApplicationUpdate(BaseModel):
    job_title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    salary_expectation: Optional[str] = None
    initial_contact_date: Optional[datetime] = None
    resume_id: Optional[str] = None
    tags: Optional[List[str]] = None
    match_score: Optional[float] = None
    match_explanation: Optional[str] = None
    follow_up_date: Optional[datetime] = None
    notes: Optional[str] = None


class StageChange(BaseModel):
    stage: str
    detail: Optional[str] = None


class CommunicationCreate(BaseModel):
    channel: str = "email"
    summary: str
    raw_content: Optional[str] = None
