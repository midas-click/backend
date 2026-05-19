"""Applications API — full CRUD + kanban stage management + communication logs."""

from datetime import datetime
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.pagination import CursorPage, add_cursor_filter, build_cursor_page
from app.auth.dependencies import get_auth_context
from app.models.application import (
    ApplicationBatchCreate,
    ApplicationCreate,
    ApplicationDocument,
    ApplicationStage,
    ApplicationUpdate,
    CommunicationCreate,
    CommunicationLog,
    StageChange,
    TimelineEvent,
)
from app.models.job import JobDocument
from app.models.resume import ResumeDocument

router = APIRouter(tags=["Applications"])


ApplicationListResponse = CursorPage[ApplicationDocument]


# ── LIST ──────────────────────────────────────────
@router.get("/applications", response_model=ApplicationListResponse)
async def list_applications(
    stage: Optional[str] = None,
    tag: Optional[str] = None,
    company: Optional[str] = None,
    search: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: int = Query(default=25, ge=1, le=100),
    ctx: dict = Depends(get_auth_context),
):
    filters: dict = {"org_id": ctx["org_id"]}
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
            {"tags": {"$regex": search, "$options": "i"}},
        ]
    try:
        add_cursor_filter(filters, cursor, "updated_at")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid cursor") from exc

    items = (
        await ApplicationDocument.find(filters)
        .sort("-updated_at", "-_id")
        .limit(limit + 1)
        .to_list()
    )
    return build_cursor_page(items, limit, "updated_at")


# ── GET ───────────────────────────────────────────
@router.get("/applications/{app_id}", response_model=ApplicationDocument)
async def get_application(app_id: str, ctx: dict = Depends(get_auth_context)):
    app = await ApplicationDocument.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    if app.org_id != ctx["org_id"]:
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
            if job.org_id == ctx["org_id"] and job.source_url:
                create_data["source_url"] = job.source_url

    # Auto-populate resume_filename from linked Resume if not explicitly provided
    if not create_data.get("resume_filename") and create_data.get("resume_id"):
        resume = await ResumeDocument.get(create_data["resume_id"])
        if resume and resume.org_id == ctx["org_id"]:
            create_data["resume_filename"] = resume.original_filename

    app = ApplicationDocument(
        user_id=ctx["user_id"],
        org_id=ctx["org_id"],
        profile_id=ctx["profile_id"],
        **create_data,
        timeline=[TimelineEvent(event="Applied", detail="Application created")],
    )
    return await app.insert()


@router.post("/applications/batch", response_model=list[ApplicationDocument], status_code=status.HTTP_201_CREATED)
async def create_applications_batch(payload: ApplicationBatchCreate, ctx: dict = Depends(get_auth_context)):
    job_ids = list(dict.fromkeys(payload.job_ids))
    object_ids = [ObjectId(job_id) for job_id in job_ids if ObjectId.is_valid(job_id)]
    if len(object_ids) != len(job_ids):
        raise HTTPException(status_code=400, detail="One or more selected job IDs are invalid")

    resume_filter = {"org_id": ctx["org_id"]}
    if ctx["profile_id"]:
        resume_filter["profile_id"] = ctx["profile_id"]
    resume = await ResumeDocument.find(resume_filter).sort("-created_at").first_or_none()
    if not resume:
        raise HTTPException(status_code=400, detail="Upload at least one resume before creating applications.")

    jobs = await JobDocument.find({"_id": {"$in": object_ids}}).to_list()
    jobs_by_id = {str(job.id): job for job in jobs}
    missing_ids = [job_id for job_id in job_ids if job_id not in jobs_by_id]
    if missing_ids:
        raise HTTPException(status_code=404, detail="One or more selected jobs were not found")

    applications: list[ApplicationDocument] = []
    for job_id in job_ids:
        job = jobs_by_id[job_id]
        app = ApplicationDocument(
            user_id=ctx["user_id"],
            org_id=ctx["org_id"],
            profile_id=ctx["profile_id"],
            job_id=str(job.id),
            job_title=job.title,
            company=job.company,
            stage=ApplicationStage.APPLIED.value,
            location=job.location or "",
            source_url=job.source_url,
            salary_expectation=job.salary_range,
            tags=job.tags,
            notes=job.description,
            resume_id=str(resume.id),
            resume_filename=resume.original_filename,
            timeline=[TimelineEvent(event="Applied", detail="Application created")],
        )
        applications.append(await app.insert())

    return applications


# ── UPDATE ────────────────────────────────────────
@router.patch("/applications/{app_id}", response_model=ApplicationDocument)
async def update_application(app_id: str, payload: ApplicationUpdate, ctx: dict = Depends(get_auth_context)):
    app = await ApplicationDocument.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    if app.org_id != ctx["org_id"]:
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
    if app.org_id != ctx["org_id"]:
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
    if app.org_id != ctx["org_id"]:
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
    if app.org_id != ctx["org_id"]:
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
