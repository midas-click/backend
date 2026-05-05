"""Jobs API — manual entry, listing, bookmarking."""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.models.job import JobCreate, JobDocument

router = APIRouter(tags=["Jobs"])


@router.get("/jobs", response_model=List[JobDocument])
async def list_jobs(
    status_filter: Optional[str] = Query(None, alias="status"),
    tag: Optional[str] = None,
    search: Optional[str] = None,
    user_id: str = "default",
):
    filters = {"user_id": user_id}
    if status_filter:
        filters["status"] = status_filter
    if tag:
        filters["tags"] = tag
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


@router.post("/jobs", response_model=JobDocument, status_code=status.HTTP_201_CREATED)
async def create_job(payload: JobCreate, user_id: str = "default"):
    job = JobDocument(user_id=user_id, **payload.model_dump())
    return await job.insert()


@router.patch("/jobs/{job_id}/status", response_model=JobDocument)
async def update_job_status(job_id: str, status_val: str = Query(..., alias="status")):
    job = await JobDocument.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if status_val not in ("saved", "applied", "archived"):
        raise HTTPException(status_code=400, detail="Invalid status")
    job.status = status_val
    return await job.save()


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: str):
    job = await JobDocument.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await job.delete()
