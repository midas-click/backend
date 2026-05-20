"""Jobs API — public listing, authenticated creation/management with role-based access."""

import logging
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError

from app.api.pagination import CursorPage, add_cursor_filter, build_cursor_page
from app.auth.dependencies import (
    get_auth_context,
    get_current_profile_id,
    get_optional_auth_context,
)
from app.config import settings
from app.models.application import ApplicationDocument
from app.models.job import JobAnalyzeRequest, JobCreate, JobDocument, JobUpdate
from app.models.resume import ResumeDocument
from app.services.job_chunk_service import (
    JobChunkServiceError,
    delete_job_chunks,
    replace_job_chunks,
)
from app.services.llm_service import extract_job_fields
from app.services.match_score_service import ResumeMatchScore, score_resumes_for_job

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Jobs"])

# Roles that can manage any job in their organization
_MANAGER_ROLES = {"org:admin"}


JobListResponse = CursorPage[JobDocument]


def _can_manage(job: JobDocument, user_id: str, org_id: str, org_role: str) -> bool:
    """Check if the current user can edit/delete this job."""
    if job.user_id == user_id:
        return True
    if org_role in _MANAGER_ROLES and job.org_id == org_id:
        return True
    return False


def _normalize_source_url(source_url: str | None) -> str | None:
    url = (source_url or "").strip()
    return url.rstrip("/") if url else None


async def _ensure_source_url_available(source_url: str | None, exclude_job_id: str | None = None) -> str:
    normalized_url = _normalize_source_url(source_url)
    if not normalized_url:
        raise HTTPException(status_code=400, detail="Job posting URL is required")

    existing = await JobDocument.find_one(JobDocument.source_url == normalized_url)
    if existing and str(existing.id) != exclude_job_id:
        raise HTTPException(status_code=409, detail="A job with this posting URL already exists")
    return normalized_url


def _duplicate_source_url_error() -> HTTPException:
    return HTTPException(status_code=409, detail="A job with this posting URL already exists")


# ── LIST (public) ────────────────────────────────
@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    tag: Optional[str] = None,
    search: Optional[str] = None,
    creator: str = Query(default="all", pattern="^(all|me|org)$"),
    cursor: Optional[str] = None,
    limit: int = Query(default=25, ge=1, le=100),
    profile_id: Optional[str] = Depends(get_current_profile_id),
    auth_ctx: Optional[dict] = Depends(get_optional_auth_context),
):
    """List jobs — publicly accessible, no auth required.

    When a profile is active (X-Profile-Id header), jobs that already have
    an application for that profile are excluded from the list.
    """
    filters: dict = {}
    if tag:
        filters["tags"] = {"$regex": tag, "$options": "i"}
    if search:
        filters["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"company": {"$regex": search, "$options": "i"}},
            {"location": {"$regex": search, "$options": "i"}},
            {"tags": {"$regex": search, "$options": "i"}},
        ]
    if creator != "all":
        if not auth_ctx:
            raise HTTPException(status_code=401, detail="Authentication required for creator filter")
        if creator == "me":
            filters["user_id"] = auth_ctx["user_id"]
        elif creator == "org":
            filters["org_id"] = auth_ctx["org_id"]

    if profile_id:
        applied = await ApplicationDocument.find(
            {"profile_id": profile_id}
        ).to_list()
        applied_job_ids = [
            ObjectId(app.job_id)
            for app in applied
            if app.job_id and ObjectId.is_valid(app.job_id)
        ]
        if applied_job_ids:
            filters["_id"] = {"$nin": applied_job_ids}

    try:
        add_cursor_filter(filters, cursor, "created_at")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid cursor") from exc

    jobs = (
        await JobDocument.find(filters)
        .sort("-created_at", "-_id")
        .limit(limit + 1)
        .to_list()
    )
    return build_cursor_page(jobs, limit, "created_at")


# ── GET (public) ──────────────────────────────────
@router.get("/jobs/{job_id}", response_model=JobDocument)
async def get_job(job_id: str):
    """Get a single job — publicly accessible."""
    job = await JobDocument.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/jobs/{job_id}/resume-match-scores", response_model=list[ResumeMatchScore])
async def get_resume_match_scores(
    job_id: str,
    ctx: dict = Depends(get_auth_context),
):
    job = await JobDocument.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    resume_filter = {"org_id": ctx["org_id"]}
    if ctx["profile_id"]:
        resume_filter["profile_id"] = ctx["profile_id"]
    resumes = await ResumeDocument.find(resume_filter).sort("-created_at").to_list()
    return await score_resumes_for_job(job_id, resumes, ctx["org_id"])


# ── CREATE (authenticated) ────────────────────────
@router.post("/jobs/analyze", response_model=JobDocument, status_code=status.HTTP_201_CREATED)
async def analyze_and_create_job(
    payload: JobAnalyzeRequest,
    ctx: dict = Depends(get_auth_context),
):
    """Paste a raw job description, let LLM extract structured fields, and save."""
    if not payload.raw_text.strip():
        raise HTTPException(status_code=400, detail="Job description is required")
    source_url = await _ensure_source_url_available(payload.source_url)

    try:
        extracted = await extract_job_fields(payload.raw_text.strip())
    except Exception as e:
        logger.exception("LLM extraction failed")
        raise HTTPException(status_code=502, detail=f"AI extraction failed: {e}") from e

    job = JobDocument(
        user_id=ctx["user_id"],
        org_id=ctx["org_id"],
        title=extracted.get("title") or "Untitled",
        company=extracted.get("company") or "Unknown",
        description=payload.raw_text.strip(),
        location=extracted.get("location"),
        remote=bool(extracted.get("remote", False)),
        salary_range=extracted.get("salary_range"),
        org_name=ctx["org_name"],
        source_url=source_url,
        tags=extracted.get("tags", []),
    )
    try:
        job = await job.insert()
        if settings.EMBEDDINGS_ENABLED:
            # Temporarily disabled on low-memory Render instances.
            # Re-enable by setting EMBEDDINGS_ENABLED=true after upgrading the service.
            try:
                await replace_job_chunks(job)
            except JobChunkServiceError as exc:
                logger.exception("Job embedding failed for job_id=%s", job.id)
                await job.delete()
                raise HTTPException(status_code=502, detail=str(exc)) from exc
        return job
    except DuplicateKeyError as exc:
        raise _duplicate_source_url_error() from exc


@router.post("/jobs", response_model=JobDocument, status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: JobCreate,
    ctx: dict = Depends(get_auth_context),
):
    """Create a job — requires authentication."""
    create_data = payload.model_dump()
    if create_data.get("source_url"):
        create_data["source_url"] = await _ensure_source_url_available(create_data["source_url"])
    job = JobDocument(
        user_id=ctx["user_id"],
        org_id=ctx["org_id"],
        org_name=ctx["org_name"],
        **create_data,
    )
    try:
        job = await job.insert()
        if settings.EMBEDDINGS_ENABLED:
            # Temporarily disabled on low-memory Render instances.
            # Re-enable by setting EMBEDDINGS_ENABLED=true after upgrading the service.
            try:
                await replace_job_chunks(job)
            except JobChunkServiceError as exc:
                logger.exception("Job embedding failed for job_id=%s", job.id)
                await job.delete()
                raise HTTPException(status_code=502, detail=str(exc)) from exc
        return job
    except DuplicateKeyError as exc:
        raise _duplicate_source_url_error() from exc


# ── UPDATE (owner or team_manager) ────────────────
@router.patch("/jobs/{job_id}", response_model=JobDocument)
async def update_job(
    job_id: str,
    payload: JobUpdate,
    ctx: dict = Depends(get_auth_context),
):
    """Update a job — only the creator or a team manager can edit."""
    job = await JobDocument.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not _can_manage(job, ctx["user_id"], ctx["org_id"], ctx["org_role"]):
        raise HTTPException(status_code=403, detail="Not authorized to edit this job")
    update_data = payload.model_dump(exclude_unset=True)
    if "source_url" in update_data and update_data["source_url"]:
        update_data["source_url"] = await _ensure_source_url_available(update_data["source_url"], job_id)
    for field, value in update_data.items():
        setattr(job, field, value)
    try:
        job = await job.save()
        if settings.EMBEDDINGS_ENABLED and _job_embedding_fields_changed(update_data):
            # Temporarily disabled on low-memory Render instances.
            # Re-enable by setting EMBEDDINGS_ENABLED=true after upgrading the service.
            try:
                await replace_job_chunks(job)
            except JobChunkServiceError as exc:
                logger.exception("Job embedding update failed for job_id=%s", job.id)
                raise HTTPException(status_code=502, detail=str(exc)) from exc
        return job
    except DuplicateKeyError as exc:
        raise _duplicate_source_url_error() from exc


# ── DELETE (owner or team_manager) ────────────────
@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: str,
    ctx: dict = Depends(get_auth_context),
):
    """Delete a job — only the creator or a team manager can delete."""
    job = await JobDocument.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not _can_manage(job, ctx["user_id"], ctx["org_id"], ctx["org_role"]):
        raise HTTPException(status_code=403, detail="Not authorized to delete this job")
    await delete_job_chunks(job_id)
    await job.delete()


def _job_embedding_fields_changed(update_data: dict) -> bool:
    return bool({"title", "company", "description", "location", "salary_range", "tags"} & update_data.keys())
