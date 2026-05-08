"""Application model — the core ATS entity."""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from beanie import Document, Indexed
from pydantic import BaseModel, Field, field_validator

from app.models.base import MidasDocument


# ── Enums ────────────────────────────────────
class ApplicationStage(str, Enum):
    APPLIED = "applied"
    PHONE_SCREEN = "phone_screen"
    TECHNICAL = "technical"
    ONSITE = "onsite"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


KANBAN_ORDER = [
    ApplicationStage.APPLIED,
    ApplicationStage.PHONE_SCREEN,
    ApplicationStage.TECHNICAL,
    ApplicationStage.ONSITE,
    ApplicationStage.OFFER,
]

DEFAULT_STAGES: list[str] = [
    ApplicationStage.APPLIED.value,
    ApplicationStage.PHONE_SCREEN.value,
    ApplicationStage.TECHNICAL.value,
    ApplicationStage.ONSITE.value,
    ApplicationStage.OFFER.value,
]


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

    user_id: str = Field(default="default")  # placeholder — will be JWT subject later
    job_id: Optional[str] = None  # links to source Job
    job_title: str
    company: str
    location: Optional[str] = None
    salary_expectation: Optional[str] = None

    @field_validator("salary_expectation", mode="before")
    @classmethod
    def _coerce_salary(cls, v):
        if v is None:
            return None
        return str(int(v)) if isinstance(v, float) and v == int(v) else str(v) if isinstance(v, (int, float)) else str(v)

    stage: str = ApplicationStage.APPLIED.value
    initial_contact_date: Optional[datetime] = None
    resume_ids: List[str] = Field(default_factory=list)

    tags: List[str] = Field(default_factory=list)  # e.g. ["react", "healthtech"]

    match_score: Optional[str] = None         # 0-100
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
    salary_expectation: Optional[str] = None
    initial_contact_date: Optional[datetime] = None
    resume_ids: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class ApplicationUpdate(BaseModel):
    job_title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    salary_expectation: Optional[str] = None
    initial_contact_date: Optional[datetime] = None
    resume_ids: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    match_score: Optional[str] = None
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
