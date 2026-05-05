"""Tailoring API — LLM-assisted resume tailoring + match scoring + interview prep."""

from datetime import datetime
from typing import List, Optional
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.models.application import ApplicationDocument
from app.models.resume import ResumeDocument
from app.services.tailoring_service import (
    compute_match_score,
    extract_keywords_from_job,
    generate_interview_questions,
    generate_tailored_resume,
)
from app.services.s3_service import generate_presigned_download_url

router = APIRouter(tags=["Tailoring"])


# ── Request schemas ───────────────────────────────
class TailorRequest(BaseModel):
    resume_id: str
    job_description: str
    job_title: Optional[str] = None
    company: Optional[str] = None


class TailorResponse(BaseModel):
    tailored_resume_id: str
    tailored_text: str
    missing_keywords: List[str]
    improvements: List[str] = Field(default_factory=list)


class MatchScoreRequest(BaseModel):
    resume_id: str
    job_description: str


class MatchScoreResponse(BaseModel):
    score: float
    explanation: str
    keywords: List[str]


class InterviewQuestionsRequest(BaseModel):
    job_description: str
    role: str = ""


class InterviewQuestionsResponse(BaseModel):
    behavioral: List[str]
    technical: List[str]
    role_specific: List[str]


# ── TAILOR RESUME ─────────────────────────────────
@router.post("/tailor", response_model=TailorResponse)
async def tailor_resume(payload: TailorRequest, user_id: str = "default"):
    """Generate a tailored resume version for a specific job description."""
    base = await ResumeDocument.get(payload.resume_id)
    if not base or not base.raw_text:
        raise HTTPException(status_code=404, detail="Resume not found or has no parsed text")

    # 1. Extract keywords from job
    job_keywords = await extract_keywords_from_job(payload.job_description)

    # 2. Find missing keywords (simple intersection check)
    resume_lower = base.raw_text.lower()
    missing = [kw for kw in job_keywords if kw.lower() not in resume_lower]

    # 3. Generate tailored resume
    tailored_text = await generate_tailored_resume(
        base_resume_text=base.raw_text,
        job_description=payload.job_description,
        missing_keywords=missing,
    )

    # 4. Save as new version in DB (+ S3 placeholder)
    version = await ResumeDocument.find(
        ResumeDocument.parent_resume_id == payload.resume_id,
    ).count() + 1

    tailored = ResumeDocument(
        user_id=user_id,
        original_filename=f"tailored_{base.original_filename}",
        s3_key=f"resumes/tailored/{uuid.uuid4().hex}.txt",
        s3_url=None,
        raw_text=tailored_text,
        sections=[],
        parent_resume_id=payload.resume_id,
        version=version,
        tags=base.tags,
    )
    await tailored.insert()

    return TailorResponse(
        tailored_resume_id=str(tailored.id),
        tailored_text=tailored_text,
        missing_keywords=missing,
        improvements=[
            f"Incorporate '{kw}' — this keyword appears in the job description but is missing from your resume."
            for kw in missing[:8]
        ],
    )


# ── MATCH SCORE ───────────────────────────────────
@router.post("/match-score", response_model=MatchScoreResponse)
async def get_match_score(payload: MatchScoreRequest):
    """Compare a resume against a job description and return a match score."""
    resume = await ResumeDocument.get(payload.resume_id)
    if not resume or not resume.raw_text:
        raise HTTPException(status_code=404, detail="Resume not found or has no parsed text")

    keywords = await extract_keywords_from_job(payload.job_description)
    score, explanation = await compute_match_score(
        resume_text=resume.raw_text,
        job_description=payload.job_description,
        job_keywords=keywords,
    )

    # Optionally update the application match score if linked
    # (skipped for simplicity — call this endpoint then PATCH the app)

    return MatchScoreResponse(score=score, explanation=explanation, keywords=keywords)


# ── INTERVIEW QUESTIONS ───────────────────────────
@router.post("/interview-questions", response_model=InterviewQuestionsResponse)
async def get_interview_questions(payload: InterviewQuestionsRequest):
    """Generate likely interview questions from a job description."""
    questions = await generate_interview_questions(
        job_description=payload.job_description,
        role=payload.role,
    )
    return InterviewQuestionsResponse(
        behavioral=questions.get("behavioral", []),
        technical=questions.get("technical", []),
        role_specific=questions.get("role_specific", []),
    )
