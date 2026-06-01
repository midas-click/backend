"""Application model — the core ATS entity."""

from datetime import UTC, datetime
from enum import Enum

from beanie import Document
from pydantic import BaseModel, Field
from pymongo import ASCENDING, DESCENDING, IndexModel

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
    date: datetime = Field(default_factory=lambda: datetime.now(UTC))
    channel: str = "email"  # email | phone | linkedin | in_person
    summary: str
    raw_content: str | None = None


class TimelineEvent(BaseModel):
    date: datetime = Field(default_factory=lambda: datetime.now(UTC))
    event: str  # e.g. "Applied", "Phone screen scheduled"
    detail: str | None = None


# ── Main document ────────────────────────────
class ApplicationDocument(Document, MidasDocument):
    """Stores a single job application tracked through the pipeline."""

    user_id: str = Field(default="default")  # Clerk user ID (sub claim)
    org_id: str = Field(default="default")  # Clerk organization ID (org_id claim)
    profile_id: str | None = None         # active profile ID
    job_id: str | None = None  # links to source Job
    job_title: str
    company: str
    location: str | None = None
    source_url: str | None = None  # denormalized from Job — survives job deletion
    salary_expectation: str | None = None

    stage: str = ApplicationStage.APPLIED.value
    initial_contact_date: datetime | None = None
    resume_id: str | None = None
    resume_filename: str | None = None  # denormalized from Resume — survives resume deletion

    tags: list[str] = Field(default_factory=list)  # e.g. ["react", "healthtech"]

    match_score: float | None = None         # 0-100
    match_explanation: str | None = None

    communication_log: list[CommunicationLog] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)

    follow_up_date: datetime | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "applications"
        indexes = [
            IndexModel(
                [("org_id", ASCENDING), ("updated_at", DESCENDING), ("_id", DESCENDING)],
                name="apps_org_updated_cursor",
            ),
            IndexModel(
                [("org_id", ASCENDING), ("stage", ASCENDING), ("updated_at", DESCENDING), ("_id", DESCENDING)],
                name="apps_org_stage_updated_cursor",
            ),
            IndexModel(
                [("org_id", ASCENDING), ("profile_id", ASCENDING), ("updated_at", DESCENDING), ("_id", DESCENDING)],
                name="apps_profile_updated_cursor",
            ),
            IndexModel(
                [
                    ("org_id", ASCENDING),
                    ("profile_id", ASCENDING),
                    ("stage", ASCENDING),
                    ("updated_at", DESCENDING),
                    ("_id", DESCENDING),
                ],
                name="apps_profile_stage_updated_cursor",
            ),
            IndexModel(
                [("profile_id", ASCENDING), ("job_id", ASCENDING)],
                name="apps_profile_job_lookup",
            ),
            IndexModel(
                [("profile_id", ASCENDING), ("created_at", DESCENDING), ("job_id", ASCENDING)],
                name="apps_profile_recent_jobs_lookup",
            ),
            IndexModel(
                [("resume_id", ASCENDING)],
                name="apps_resume_lookup",
            ),
            IndexModel(
                [("org_id", ASCENDING), ("profile_id", ASCENDING), ("created_at", DESCENDING)],
                name="apps_profile_created_analytics",
            ),
        ]


# ── API request / response schemas (Pydantic) ──
class ApplicationCreate(BaseModel):
    job_id: str | None = None
    job_title: str
    company: str
    stage: str | None = None
    location: str | None = None
    source_url: str | None = None
    salary_expectation: str | None = None
    initial_contact_date: datetime | None = None
    resume_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    match_score: float | None = None
    match_explanation: str | None = None


class ApplicationBatchCreate(BaseModel):
    job_ids: list[str] = Field(min_length=1, max_length=100)


class StageChange(BaseModel):
    stage: str
    detail: str | None = None


class CommunicationCreate(BaseModel):
    channel: str = "email"
    summary: str
    raw_content: str | None = None
