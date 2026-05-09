"""Applications API — full CRUD + kanban stage management + communication logs."""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

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


# ── LIST ──────────────────────────────────────────
@router.get("/applications", response_model=List[ApplicationDocument])
async def list_applications(
    stage: Optional[str] = None,
    tag: Optional[str] = None,
    company: Optional[str] = None,
    search: Optional[str] = None,
    user_id: str = "default",
):
    filters: dict = {"user_id": user_id}
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
async def get_application(app_id: str):
    app = await ApplicationDocument.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


# ── CREATE ────────────────────────────────────────
@router.post("/applications", response_model=ApplicationDocument, status_code=status.HTTP_201_CREATED)
async def create_application(payload: ApplicationCreate, user_id: str = "default"):
    create_data = payload.model_dump(exclude_unset=True)

    # Auto-populate source_url from linked Job if not explicitly provided
    if not create_data.get("source_url") and create_data.get("job_id"):
        job = await JobDocument.get(create_data["job_id"])
        if job and job.source_url:
            create_data["source_url"] = job.source_url

    # Auto-populate resume_filename from linked Resume if not explicitly provided
    if not create_data.get("resume_filename") and create_data.get("resume_id"):
        resume = await ResumeDocument.get(create_data["resume_id"])
        if resume:
            create_data["resume_filename"] = resume.original_filename

    app = ApplicationDocument(
        user_id=user_id,
        **create_data,
        timeline=[TimelineEvent(event="Applied", detail="Application created")],
    )
    return await app.insert()


# ── UPDATE ────────────────────────────────────────
@router.patch("/applications/{app_id}", response_model=ApplicationDocument)
async def update_application(app_id: str, payload: ApplicationUpdate):
    app = await ApplicationDocument.get(app_id)
    if not app:
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
async def delete_application(app_id: str):
    app = await ApplicationDocument.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    await app.delete()


# ── MOVE STAGE (Kanban) ───────────────────────────
@router.patch("/applications/{app_id}/stage", response_model=ApplicationDocument)
async def move_stage(app_id: str, payload: StageChange):
    app = await ApplicationDocument.get(app_id)
    if not app:
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
async def add_communication(app_id: str, payload: CommunicationCreate):
    app = await ApplicationDocument.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    app.communication_log.append(CommunicationLog(**payload.model_dump()))
    app.timeline.append(TimelineEvent(
        event=f"Communication: {payload.channel}",
        detail=payload.summary,
    ))
    app.updated_at = datetime.utcnow()
    return await app.save()
