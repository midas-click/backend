"""Profile model — user-defined sub-accounts within a team."""

from datetime import UTC, datetime

from beanie import Document
from pydantic import BaseModel, Field

from app.models.base import MidasDocument


class ProfileDocument(Document, MidasDocument):
    """A named profile representing a specific job-seeking persona.

    Each Clerk user can create multiple profiles within a team.
    Applications, resumes, and jobs are scoped to a profile.
    """

    user_id: str                          # Clerk user ID (sub claim)
    org_id: str                          # Clerk organization ID (org_id claim)
    name: str
    email: str | None = None
    headline: str | None = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "profiles"
        indexes = [
            "user_id",
            "org_id",
            ("org_id", "user_id"),
        ]


# ── API request schemas ──

class ProfileCreate(BaseModel):
    name: str
    email: str | None = None
    headline: str | None = None


class ProfileUpdate(BaseModel):
    name: str | None = None
    headline: str | None = None
    is_active: bool | None = None
