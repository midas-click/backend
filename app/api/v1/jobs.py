"""Jobs API — public listing, authenticated creation/management."""

from typing import List, Optional

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.dependencies import get_current_user_id
from app.models.job import JobAnalyzeRequest, JobCreate, JobDocument, JobUpdate
from app.services.llm_service import extract_job_fields

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Jobs"])


# ── LIST (public) ────────────────────────────────
@router.get("/jobs", response_model=List[JobDocument])
async def list_jobs(
    tag: Optional[str] = None,
    search: Optional[str] = None,
):
    """List all jobs — publicly accessible, no auth required."""
    filters: dict = {}
    if tag:
        filters["tags"] = {"$regex": tag, "$options": "i"}
    if search:
        filters["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"company": {"$regex": search, "$options": "i"}},
        ]

    return await JobDocument.find(filters).sort("-created_at").to_list()


# ── GET (public) ──────────────────────────────────
@router.get("/jobs/{job_id}", response_model=JobDocument)
async def get_job(job_id: str):
    """Get a single job — publicly accessible."""
    job = await JobDocument.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# ── CREATE (authenticated) ────────────────────────
@router.post("/jobs/analyze", response_model=JobDocument, status_code=status.HTTP_201_CREATED)
async def analyze_and_create_job(
    payload: JobAnalyzeRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Paste a raw job description, let LLM extract structured fields, and save."""
    if not payload.raw_text.strip():
        raise HTTPException(status_code=400, detail="Job description is required")

    try:
        extracted = await extract_job_fields(payload.raw_text.strip())
    except Exception as e:
        logger.exception("LLM extraction failed")
        raise HTTPException(status_code=502, detail=f"AI extraction failed: {e}")

    job = JobDocument(
        user_id=user_id,
        title=extracted.get("title") or "Untitled",
        company=extracted.get("company") or "Unknown",
        description=payload.raw_text.strip(),
        location=extracted.get("location"),
        remote=bool(extracted.get("remote", False)),
        salary_range=extracted.get("salary_range"),
        source_name="ai-analyzed",
        source_url=payload.source_url or None,
        tags=extracted.get("tags", []),
    )
    return await job.insert()


@router.post("/jobs", response_model=JobDocument, status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: JobCreate,
    user_id: str = Depends(get_current_user_id),
):
    """Create a job — requires authentication."""
    job = JobDocument(
        user_id=user_id,
        **payload.model_dump(),
    )
    return await job.insert()


# ── UPDATE (owner only) ───────────────────────────
@router.patch("/jobs/{job_id}", response_model=JobDocument)
async def update_job(
    job_id: str,
    payload: JobUpdate,
    user_id: str = Depends(get_current_user_id),
):
    job = await JobDocument.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to edit this job")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(job, field, value)
    return await job.save()


# ── DELETE (owner only) ──────────────────────────
@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: str,
    user_id: str = Depends(get_current_user_id),
):
    job = await JobDocument.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this job")
    await job.delete()
