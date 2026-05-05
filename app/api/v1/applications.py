"""Applications API — full CRUD + kanban stage management + communication logs."""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.models.application import (
    ApplicationCreate,
    ApplicationDocument,
    ApplicationStage,
    ApplicationUpdate,
    CommunicationCreate,
    CommunicationLog,
    StageChange,
    TimelineEvent,
)

router = APIRouter(tags=["Applications"])


# ── LIST ──────────────────────────────────────────
@router.get("/applications", response_model=List[ApplicationDocument])
async def list_applications(
    stage: Optional[ApplicationStage] = None,
    tag: Optional[str] = None,
    company: Optional[str] = None,
    user_id: str = "default",
):
    filters = {"user_id": user_id}
    if stage:
        filters["stage"] = stage
    if tag:
        filters["tags"] = tag
    if company:
        filters["company"] = {"$regex": company, "$options": "i"}
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
    app = ApplicationDocument(
        user_id=user_id,
        **payload.model_dump(),
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
        event=f"Moved: {old_stage.value} → {payload.stage.value}",
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
