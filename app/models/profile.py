"""Profile model — user-defined sub-accounts within a team."""

from datetime import datetime
from typing import Optional

from beanie import Document
from pydantic import BaseModel, Field

from app.models.base import MidasDocument


class ProfileDocument(Document, MidasDocument):
    """A named profile representing a specific job-seeking persona.

    Each Clerk user can create multiple profiles within a team.
    Applications, resumes, and jobs are scoped to a profile.
    """

    user_id: str                          # Clerk user ID (sub claim)
    team_id: str                          # Clerk organization ID (org_id claim)
    name: str
    email: Optional[str] = None
    headline: Optional[str] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "profiles"
        indexes = [
            "user_id",
            "team_id",
            ("team_id", "user_id"),
        ]


# ── API request schemas ──

class ProfileCreate(BaseModel):
    name: str
    email: Optional[str] = None
    headline: Optional[str] = None


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    headline: Optional[str] = None
    is_active: Optional[bool] = None
