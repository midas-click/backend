"""Resumes API — upload, list, parse, version management."""

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.models.resume import ResumeDocument
from app.services.resume_parser import parse_resume_bytes
from app.services.s3_service import generate_presigned_upload_url, generate_presigned_download_url

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

    # Store in S3 (optional — skip if no S3 configured)
    s3_key = f"resumes/{uuid.uuid4().hex}/{file.filename}"
    s3_url = None
    try:
        import boto3
        from app.config import settings
        client = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        )
        client.put_object(Bucket=settings.S3_BUCKET_NAME, Key=s3_key, Body=content, ContentType=file.content_type or "application/octet-stream")
        s3_url = generate_presigned_download_url(s3_key)
    except Exception:
        # S3 unavailable — store locally; URL will be None
        pass

    resume = ResumeDocument(
        user_id=user_id,
        original_filename=file.filename or "unknown",
        s3_key=s3_key,
        s3_url=s3_url,
        raw_text=raw_text_trim,
        sections=sections,
        version=1,
        tags=[],
    )
    return await resume.insert()


# ── LIST ──────────────────────────────────────────
@router.get("/resumes", response_model=List[ResumeDocument])
async def list_resumes(user_id: str = "default", parent_only: bool = False):
    query = {"user_id": user_id}
    if parent_only:
        query["parent_resume_id"] = None
    return await ResumeDocument.find(query).sort("-created_at").to_list()


# ── GET ───────────────────────────────────────────
@router.get("/resumes/{resume_id}", response_model=ResumeDocument)
async def get_resume(resume_id: str):
    resume = await ResumeDocument.get(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    return resume


# ── DELETE ────────────────────────────────────────
@router.delete("/resumes/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resume(resume_id: str):
    resume = await ResumeDocument.get(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    await resume.delete()


# ── VERSION HISTORY ───────────────────────────────
@router.get("/resumes/{resume_id}/versions", response_model=List[ResumeDocument])
async def get_resume_versions(resume_id: str):
    """Get all tailored versions derived from a base resume."""
    base = await ResumeDocument.get(resume_id)
    if not base:
        raise HTTPException(status_code=404, detail="Resume not found")

    return await ResumeDocument.find(
        ResumeDocument.parent_resume_id == resume_id,
    ).sort("version").to_list()
