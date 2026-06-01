"""Applications API — application tracking, kanban stage management, and communication logs."""

from datetime import UTC, datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.pagination import CursorPage, add_cursor_filter, build_cursor_page
from app.auth.dependencies import get_auth_context
from app.models.application import (
    ApplicationBatchCreate,
    ApplicationCreate,
    ApplicationDocument,
    ApplicationStage,
    CommunicationCreate,
    CommunicationLog,
    StageChange,
    TimelineEvent,
)
from app.models.job import JobDocument
from app.models.resume import ResumeDocument
from app.services.match_score_service import calculate_match_score_detail, score_resume_for_job

router = APIRouter(tags=["Applications"])


ApplicationListResponse = CursorPage[ApplicationDocument]


def _require_application(app: ApplicationDocument | None, ctx: dict) -> ApplicationDocument:
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    if app.org_id != ctx["org_id"]:
        raise HTTPException(status_code=404, detail="Application not found")
    if ctx["profile_id"] and app.profile_id != ctx["profile_id"]:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


# ── LIST ──────────────────────────────────────────
@router.get("/applications", response_model=ApplicationListResponse)
async def list_applications(
    stage: str | None = None,
    tag: str | None = None,
    company: str | None = None,
    search: str | None = None,
    cursor: str | None = None,
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
    return _require_application(await ApplicationDocument.get(app_id), ctx)


# ── CREATE ────────────────────────────────────────
@router.post("/applications", response_model=ApplicationDocument, status_code=status.HTTP_201_CREATED)
async def create_application(payload: ApplicationCreate, ctx: dict = Depends(get_auth_context)):
    create_data = payload.model_dump(exclude_unset=True)

    # Auto-populate source_url from linked Job if not explicitly provided
    if not create_data.get("source_url") and create_data.get("job_id"):
        job = await JobDocument.get(create_data["job_id"])
        if job and job.source_url:
            create_data["source_url"] = job.source_url

    # Auto-populate resume_filename from linked Resume if not explicitly provided
    if not create_data.get("resume_filename") and create_data.get("resume_id"):
        resume = await ResumeDocument.get(create_data["resume_id"])
        if resume and resume.org_id == ctx["org_id"]:
            create_data["resume_filename"] = resume.original_filename

    if (
        create_data.get("job_id")
        and create_data.get("resume_id")
        and create_data.get("match_score") is None
    ):
        match = await score_resume_for_job(create_data["job_id"], create_data["resume_id"], ctx["org_id"])
        if match:
            create_data["match_score"] = match.match_score
            create_data["match_explanation"] = match.match_explanation

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
        match = await calculate_match_score_detail(str(job.id), str(resume.id), ctx["org_id"], resume=resume)
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
            resume_id=str(resume.id),
            resume_filename=resume.original_filename,
            match_score=match.score,
            match_explanation=match.explanation,
            timeline=[TimelineEvent(event="Applied", detail="Application created")],
        )
        applications.append(await app.insert())

    return applications


# ── DELETE ────────────────────────────────────────
@router.delete("/applications/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(app_id: str, ctx: dict = Depends(get_auth_context)):
    if not ObjectId.is_valid(app_id):
        raise HTTPException(status_code=404, detail="Application not found")

    filters: dict = {
        "_id": ObjectId(app_id),
        "org_id": ctx["org_id"],
    }
    if ctx["profile_id"]:
        filters["profile_id"] = ctx["profile_id"]

    deleted = await ApplicationDocument.get_motor_collection().find_one_and_delete(filters)
    if not deleted:
        raise HTTPException(status_code=404, detail="Application not found")


# ── MOVE STAGE (Kanban) ───────────────────────────
@router.patch("/applications/{app_id}/stage", response_model=ApplicationDocument)
async def move_stage(app_id: str, payload: StageChange, ctx: dict = Depends(get_auth_context)):
    app = _require_application(await ApplicationDocument.get(app_id), ctx)

    old_stage = app.stage
    app.stage = payload.stage
    app.timeline.append(TimelineEvent(
        event=f"Moved: {old_stage} → {payload.stage}",
        detail=payload.detail,
    ))
    app.updated_at = datetime.now(UTC)
    return await app.save()


# ── COMMUNICATION LOGS ────────────────────────────
@router.post("/applications/{app_id}/communications", response_model=ApplicationDocument)
async def add_communication(app_id: str, payload: CommunicationCreate, ctx: dict = Depends(get_auth_context)):
    app = _require_application(await ApplicationDocument.get(app_id), ctx)

    app.communication_log.append(CommunicationLog(**payload.model_dump()))
    app.timeline.append(TimelineEvent(
        event=f"Communication: {payload.channel}",
        detail=payload.summary,
    ))
    app.updated_at = datetime.now(UTC)
    return await app.save()
