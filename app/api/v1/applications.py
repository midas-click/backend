"""Applications API — full CRUD + kanban stage management + communication logs."""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.dependencies import get_auth_context
from app.models.application import (
    ApplicationCreate,
    ApplicationDocument,
    ApplicationUpdate,
    CommunicationCreate,
    CommunicationLog,
    StageChange,
    TimelineEvent,
)
from app.models.job import JobDocument
from app.models.resume import ResumeDocument

router = APIRouter(tags=["Applications"])


def _assert_profile(obj: dict | None, ctx: dict):
    """Check that a document belongs to the current org (and profile if set)."""
    if obj is None:
        raise HTTPException(status_code=404, detail="Not found")
    if obj.get("team_id") != ctx["org_id"]:
        raise HTTPException(status_code=404, detail="Not found")
    if ctx["profile_id"] and obj.get("profile_id") != ctx["profile_id"]:
        raise HTTPException(status_code=404, detail="Not found")


# ── LIST ──────────────────────────────────────────
@router.get("/applications", response_model=List[ApplicationDocument])
async def list_applications(
    stage: Optional[str] = None,
    tag: Optional[str] = None,
    company: Optional[str] = None,
    search: Optional[str] = None,
    ctx: dict = Depends(get_auth_context),
):
    filters: dict = {"team_id": ctx["org_id"]}
    if ctx["profile_id"]:
        filters["profile_id"] = ctx["profile_id"]
    if stage:
        filters["stage"] = stage
    if tag:
        filters["tags"] = {"$regex": tag, "$options": "i"}
    if company:
        filters["company"] = {"$regex": company, "$options": "i"}
    if search:
        filters["$or"] = [
            {"job_title": {"$regex": search, "$options": "i"}},
            {"company": {"$regex": search, "$options": "i"}},
            {"location": {"$regex": search, "$options": "i"}},
        ]
    return await ApplicationDocument.find(filters).sort("-updated_at").to_list()


# ── GET ───────────────────────────────────────────
@router.get("/applications/{app_id}", response_model=ApplicationDocument)
async def get_application(app_id: str, ctx: dict = Depends(get_auth_context)):
    app = await ApplicationDocument.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    if app.team_id != ctx["org_id"]:
        raise HTTPException(status_code=404, detail="Application not found")
    if ctx["profile_id"] and app.profile_id != ctx["profile_id"]:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


# ── CREATE ────────────────────────────────────────
@router.post("/applications", response_model=ApplicationDocument, status_code=status.HTTP_201_CREATED)
async def create_application(payload: ApplicationCreate, ctx: dict = Depends(get_auth_context)):
    create_data = payload.model_dump(exclude_unset=True)

    # Auto-populate source_url from linked Job if not explicitly provided
    if not create_data.get("source_url") and create_data.get("job_id"):
        job = await JobDocument.get(create_data["job_id"])
        if job:
            # Only auto-populate if job belongs to the team
            if job.team_id == ctx["org_id"] and job.source_url:
                create_data["source_url"] = job.source_url

    # Auto-populate resume_filename from linked Resume if not explicitly provided
    if not create_data.get("resume_filename") and create_data.get("resume_id"):
        resume = await ResumeDocument.get(create_data["resume_id"])
        if resume and resume.team_id == ctx["org_id"]:
            create_data["resume_filename"] = resume.original_filename

    app = ApplicationDocument(
        user_id=ctx["user_id"],
        team_id=ctx["org_id"],
        profile_id=ctx["profile_id"],
        **create_data,
        timeline=[TimelineEvent(event="Applied", detail="Application created")],
    )
    return await app.insert()


# ── UPDATE ────────────────────────────────────────
@router.patch("/applications/{app_id}", response_model=ApplicationDocument)
async def update_application(app_id: str, payload: ApplicationUpdate, ctx: dict = Depends(get_auth_context)):
    app = await ApplicationDocument.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    if app.team_id != ctx["org_id"]:
        raise HTTPException(status_code=404, detail="Application not found")
    if ctx["profile_id"] and app.profile_id != ctx["profile_id"]:
        raise HTTPException(status_code=404, detail="Application not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(app, field, value)

    # Auto-populate resume_filename if resume_id changed
    if "resume_id" in update_data:
        resume = await ResumeDocument.get(app.resume_id) if app.resume_id else None
        app.resume_filename = resume.original_filename if resume else None

    app.updated_at = datetime.utcnow()
    return await app.save()


# ── DELETE ────────────────────────────────────────
@router.delete("/applications/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(app_id: str, ctx: dict = Depends(get_auth_context)):
    app = await ApplicationDocument.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    if app.team_id != ctx["org_id"]:
        raise HTTPException(status_code=404, detail="Application not found")
    if ctx["profile_id"] and app.profile_id != ctx["profile_id"]:
        raise HTTPException(status_code=404, detail="Application not found")
    await app.delete()


# ── MOVE STAGE (Kanban) ───────────────────────────
@router.patch("/applications/{app_id}/stage", response_model=ApplicationDocument)
async def move_stage(app_id: str, payload: StageChange, ctx: dict = Depends(get_auth_context)):
    app = await ApplicationDocument.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    if app.team_id != ctx["org_id"]:
        raise HTTPException(status_code=404, detail="Application not found")
    if ctx["profile_id"] and app.profile_id != ctx["profile_id"]:
        raise HTTPException(status_code=404, detail="Application not found")

    old_stage = app.stage
    app.stage = payload.stage
    app.timeline.append(TimelineEvent(
        event=f"Moved: {old_stage} → {payload.stage}",
        detail=payload.detail,
    ))
    app.updated_at = datetime.utcnow()
    return await app.save()


# ── COMMUNICATION LOGS ────────────────────────────
@router.post("/applications/{app_id}/communications", response_model=ApplicationDocument)
async def add_communication(app_id: str, payload: CommunicationCreate, ctx: dict = Depends(get_auth_context)):
    app = await ApplicationDocument.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    if app.team_id != ctx["org_id"]:
        raise HTTPException(status_code=404, detail="Application not found")
    if ctx["profile_id"] and app.profile_id != ctx["profile_id"]:
        raise HTTPException(status_code=404, detail="Application not found")

    app.communication_log.append(CommunicationLog(**payload.model_dump()))
    app.timeline.append(TimelineEvent(
        event=f"Communication: {payload.channel}",
        detail=payload.summary,
    ))
    app.updated_at = datetime.utcnow()
    return await app.save()
