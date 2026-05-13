"""Jobs API — public listing, authenticated creation/management with role-based access."""

from typing import List, Optional

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.dependencies import get_auth_context, get_current_profile_id, get_current_user_id
from app.models.application import ApplicationDocument
from app.models.job import JobAnalyzeRequest, JobCreate, JobDocument, JobUpdate
from app.services.llm_service import extract_job_fields

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Jobs"])

# Roles that can manage any job in their organization
_MANAGER_ROLES = {"org:admin"}


def _can_manage(job: JobDocument, user_id: str, org_id: str, org_role: str) -> bool:
    """Check if the current user can edit/delete this job."""
    if job.user_id == user_id:
        return True
    if org_role in _MANAGER_ROLES and job.org_id == org_id:
        return True
    return False


# ── LIST (public) ────────────────────────────────
@router.get("/jobs", response_model=List[JobDocument])
async def list_jobs(
    tag: Optional[str] = None,
    search: Optional[str] = None,
    profile_id: Optional[str] = Depends(get_current_profile_id),
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
        ]

    jobs = await JobDocument.find(filters).sort("-created_at").to_list()

    if profile_id:
        applied = await ApplicationDocument.find(
            {"profile_id": profile_id}
        ).to_list()
        applied_job_ids = {app.job_id for app in applied if app.job_id}
        jobs = [j for j in jobs if str(j.id) not in applied_job_ids]

    return jobs


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
    ctx: dict = Depends(get_auth_context),
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
        user_id=ctx["user_id"],
        org_id=ctx["org_id"],
        title=extracted.get("title") or "Untitled",
        company=extracted.get("company") or "Unknown",
        description=payload.raw_text.strip(),
        location=extracted.get("location"),
        remote=bool(extracted.get("remote", False)),
        salary_range=extracted.get("salary_range"),
        org_name=ctx["org_name"],
        source_url=payload.source_url or None,
        tags=extracted.get("tags", []),
    )
    return await job.insert()


@router.post("/jobs", response_model=JobDocument, status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: JobCreate,
    ctx: dict = Depends(get_auth_context),
):
    """Create a job — requires authentication."""
    job = JobDocument(
        user_id=ctx["user_id"],
        org_id=ctx["org_id"],
        org_name=ctx["org_name"],
        **payload.model_dump(),
    )
    return await job.insert()


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
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(job, field, value)
    return await job.save()


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
    await job.delete()
