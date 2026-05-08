"""Jobs API — manual entry, listing, bookmarking."""

from typing import List, Optional

import logging

from fastapi import APIRouter, HTTPException, Query, status

from app.models.job import JobAnalyzeRequest, JobCreate, JobDocument, JobUpdate
from app.services.llm_service import extract_job_fields

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Jobs"])


@router.get("/jobs", response_model=List[JobDocument])
async def list_jobs(
    tag: Optional[str] = None,
    search: Optional[str] = None,
    user_id: str = "default",
):
    filters = {"user_id": user_id}
    if tag:
        filters["tags"] = {"": tag, "": "i"}
    if search:
        filters["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"company": {"$regex": search, "$options": "i"}},
        ]

    return await JobDocument.find(filters).sort("-created_at").to_list()


@router.get("/jobs/{job_id}", response_model=JobDocument)
async def get_job(job_id: str):
    job = await JobDocument.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/jobs/analyze", response_model=JobDocument, status_code=status.HTTP_201_CREATED)
async def analyze_and_create_job(payload: JobAnalyzeRequest, user_id: str = "default"):
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
async def create_job(payload: JobCreate, user_id: str = "default"):
    job = JobDocument(user_id=user_id, **payload.model_dump())
    return await job.insert()


@router.patch("/jobs/{job_id}", response_model=JobDocument)
async def update_job(job_id: str, payload: JobUpdate):
    job = await JobDocument.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(job, field, value)
    return await job.save()


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: str):
    job = await JobDocument.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await job.delete()



