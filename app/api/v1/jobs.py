"""Jobs API — public listing and authenticated job capture."""

import logging
from datetime import UTC, datetime, timedelta
from time import perf_counter

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError

from app.api.pagination import CursorPage, add_cursor_filter, build_cursor_page
from app.auth.dependencies import (
    get_auth_context,
    get_current_profile_id,
)
from app.models.application import ApplicationDocument
from app.models.job import JobAnalyzeRequest, JobDocument, JobListItem
from app.models.resume import ResumeDocument
from app.services.embedding_queue_service import enqueue_job_embedding
from app.services.job_page_validation_service import validate_job_page
from app.services.llm_service import extract_job_fields
from app.services.match_score_service import ResumeMatchScore, score_resumes_for_job

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Jobs"])

JobListResponse = CursorPage[JobListItem]


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
    tag: str | None = None,
    search: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    profile_id: str | None = Depends(get_current_profile_id),
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
    try:
        if profile_id:
            applied_job_ids = await _get_recent_applied_job_object_ids(profile_id)
            if applied_job_ids:
                filters["_id"] = {"$nin": applied_job_ids}

        add_cursor_filter(filters, cursor, "created_at")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid cursor") from exc

    started_at = perf_counter()
    jobs = await _find_job_list_items(filters, limit + 1)
    logger.info(
        "Listed jobs profile_id=%s limit=%s items=%s elapsed=%.3fs",
        profile_id,
        limit,
        len(jobs),
        perf_counter() - started_at,
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


# ── CREATE (public, validated) ────────────────────
@router.post("/jobs/analyze", response_model=JobDocument, status_code=status.HTTP_201_CREATED)
async def analyze_and_create_job(
    payload: JobAnalyzeRequest,
):
    """Paste a raw job description, let LLM extract structured fields, and save."""
    if not payload.raw_text.strip():
        raise HTTPException(status_code=400, detail="Job description is required")
    source_url = await _ensure_source_url_available(payload.source_url)
    validation = validate_job_page(payload.raw_text, source_url)
    if not validation.is_job_page:
        logger.info(
            "Rejected non-job page source_url=%s confidence=%s signals=%s",
            source_url,
            validation.confidence,
            validation.signals,
        )
        raise HTTPException(
            status_code=422,
            detail={
                "message": f"{validation.reason}. Try opening a job posting or company careers page.",
                "confidence": validation.confidence,
                "signals": validation.signals,
                "source_url": source_url,
            },
        )

    try:
        extracted = await extract_job_fields(payload.raw_text.strip())
    except Exception as e:
        logger.exception("LLM extraction failed")
        raise HTTPException(status_code=502, detail=f"AI extraction failed: {e}") from e

    job = JobDocument(
        title=extracted.get("title") or "Untitled",
        company=extracted.get("company") or "Unknown",
        location=extracted.get("location"),
        remote=bool(extracted.get("remote", False)),
        salary_range=extracted.get("salary_range"),
        source_url=source_url,
        tags=extracted.get("tags", []),
    )
    try:
        job = await job.insert()
        await enqueue_job_embedding(job, payload.raw_text.strip())
        return job
    except DuplicateKeyError as exc:
        raise _duplicate_source_url_error() from exc


# ── DELETE (owner or team_manager) ────────────────
async def _find_job_list_items(
    filters: dict,
    limit: int,
) -> list[JobListItem]:
    cursor = JobDocument.get_motor_collection().find(
        filters,
    ).sort([("created_at", -1), ("_id", -1)]).limit(limit)
    docs = await cursor.to_list(length=limit)
    return [_job_list_item_from_doc(doc) for doc in docs]


async def _get_recent_applied_job_object_ids(profile_id: str) -> list[ObjectId]:
    since = datetime.now(UTC) - timedelta(days=3)
    cursor = ApplicationDocument.get_motor_collection().find({
        "profile_id": profile_id,
        "created_at": {"$gte": since},
    }, projection={"job_id": 1})
    applications = await cursor.to_list(length=None)
    return [
        ObjectId(app["job_id"])
        for app in applications
        if app.get("job_id") and ObjectId.is_valid(app["job_id"])
    ]


def _job_list_item_from_doc(doc: dict) -> JobListItem:
    return JobListItem(
        id=str(doc["_id"]),
        title=doc.get("title", "Untitled"),
        company=doc.get("company", "Unknown"),
        location=doc.get("location"),
        remote=doc.get("remote"),
        salary_range=doc.get("salary_range"),
        source_url=doc.get("source_url"),
        tags=doc.get("tags") or [],
        embedding_status=doc.get("embedding_status"),
        embedding_error=doc.get("embedding_error"),
        embedded_at=doc.get("embedded_at"),
        vector_store=doc.get("vector_store"),
        vector_chunk_count=doc.get("vector_chunk_count", 0),
        created_at=doc["created_at"],
    )
