"""Resumes API — upload, list, parse, version management."""

import logging
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.models.application import ApplicationDocument
from app.models.resume import ResumeDocument
from app.services.resume_parser import parse_resume_bytes
from app.services.s3_service import generate_presigned_upload_url, generate_presigned_download_url, upload_to_s3

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Resumes"])

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB


# ── PRE-SIGNED UPLOAD URL ─────────────────────────
@router.post("/resumes/upload-url")
async def get_upload_url(filename: str, content_type: str = "application/pdf"):
    """Get a pre-signed S3 URL for client-side direct upload."""
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in ("pdf", "docx", "doc", "txt"):
        raise HTTPException(status_code=400, detail="Unsupported file type")

    key = f"resumes/{uuid.uuid4().hex}/{filename}"
    url = generate_presigned_upload_url(key, content_type)
    return {"upload_url": url, "s3_key": key}


# ── SERVER-SIDE UPLOAD (simpler) ──────────────────
@router.post("/resumes/upload", status_code=status.HTTP_201_CREATED)
async def upload_resume(file: UploadFile = File(...), user_id: str = "default"):
    """Upload and parse a resume file directly through the server."""
    ext = (file.filename or "unknown.pdf").rsplit(".", 1)[-1].lower()
    if ext not in ("pdf", "docx", "doc", "txt"):
        raise HTTPException(status_code=400, detail="Unsupported file type")

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 5 MB)")

    # Parse
    raw_text, sections = await parse_resume_bytes(file.filename or "unknown", content)
    raw_text_trim = raw_text[:50000]  # cap stored text

    # Store in S3
    s3_key = f"resumes/{uuid.uuid4().hex}/{file.filename}"
    s3_url = None
    try:
        s3_url = await upload_to_s3(s3_key, content, file.content_type or "application/pdf")
    except Exception as e:
        logger.warning("S3 upload skipped: %s", e)

    resume = ResumeDocument(
        user_id=user_id,
        original_filename=file.filename or "unknown",
        s3_key=s3_key,
        s3_url=s3_url,
        raw_text=raw_text_trim,
        sections=sections,
        tags=[],
    )
    return await resume.insert()


# ── LIST ──────────────────────────────────────────
@router.get("/resumes")
async def list_resumes(user_id: str = "default"):
    resumes = await ResumeDocument.find({"user_id": user_id}).sort("-created_at").to_list()
    if not resumes:
        return []

    resume_ids = [str(r.id) for r in resumes]

    # Compute live stats from applications
    pipeline = [
        {"$match": {"resume_id": {"$in": resume_ids}}},
        {"$group": {
            "_id": "$resume_id",
            "total_applications": {"$sum": 1},
            "interview_count": {
                "$sum": {
                    "$cond": [{"$in": ["$stage", [
                        "phone_screen",
                        "technical",
                        "team_interview",
                        "offer",
                    ]]}, 1, 0],
                },
            },
            "offer_count": {
                "$sum": {"$cond": [{"$eq": ["$stage", "offer"]}, 1, 0]},
            },
        }},
    ]
    stats_list = await ApplicationDocument.aggregate(pipeline).to_list(None)
    stats_map = {s["_id"]: s for s in stats_list}

    result = []
    for r in resumes:
        data = r.model_dump()
        data["id"] = str(r.id)
        stats = stats_map.get(str(r.id), {})
        data["total_applications"] = stats.get("total_applications", 0)
        data["interview_count"] = stats.get("interview_count", 0)
        data["offer_count"] = stats.get("offer_count", 0)
        result.append(data)
    return result


# ── GET ───────────────────────────────────────────
@router.get("/resumes/{resume_id}")
async def get_resume(resume_id: str):
    resume = await ResumeDocument.get(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    # Compute live stats
    pipeline = [
        {"$match": {"resume_id": resume_id}},
        {"$group": {
            "_id": None,
            "total_applications": {"$sum": 1},
            "interview_count": {
                "$sum": {
                    "$cond": [{"$in": ["$stage", [
                        "phone_screen",
                        "technical",
                        "team_interview",
                        "offer",
                    ]]}, 1, 0],
                },
            },
            "offer_count": {
                "$sum": {"$cond": [{"$eq": ["$stage", "offer"]}, 1, 0]},
            },
        }},
    ]
    stats_list = await ApplicationDocument.aggregate(pipeline).to_list(1)
    stats = stats_list[0] if stats_list else {}

    data = resume.model_dump()
    data["id"] = str(resume.id)
    data["total_applications"] = stats.get("total_applications", 0)
    data["interview_count"] = stats.get("interview_count", 0)
    data["offer_count"] = stats.get("offer_count", 0)
    return data


class ResumeUpdate(BaseModel):
    tags: Optional[List[str]] = None


@router.patch("/resumes/{resume_id}", response_model=ResumeDocument)
async def update_resume(resume_id: str, payload: ResumeUpdate):
    resume = await ResumeDocument.get(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    if payload.tags is not None:
        resume.tags = payload.tags
    return await resume.save()


# ── DELETE ────────────────────────────────────────
@router.delete("/resumes/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resume(resume_id: str):
    resume = await ResumeDocument.get(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    await resume.delete()

