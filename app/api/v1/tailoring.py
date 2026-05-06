"""Tailoring API — LLM-assisted resume tailoring + match scoring + interview prep."""

import uuid
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.models.job import JobDocument
from app.models.resume import ResumeDocument
from app.services.tailoring_service import (
    compute_match_score,
    extract_keywords_from_job,
    generate_interview_questions,
    generate_tailored_resume,
    generate_tailored_label,
)

router = APIRouter(tags=["Tailoring"])


# ── Request schemas ───────────────────────────────
class TailorRequest(BaseModel):
    resume_id: str
    mode: str = "description"  # "job" | "description" | "keywords"
    job_id: Optional[str] = None
    job_description: Optional[str] = None
    job_title: Optional[str] = None
    company: Optional[str] = None
    keywords: Optional[str] = None  # comma-separated tech stack for "keywords" mode


class TailorResponse(BaseModel):
    tailored_resume_id: str
    tailored_text: str
    tailored_label: str
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
    """Generate a tailored resume version for a specific job or tech stack."""
    base = await ResumeDocument.get(payload.resume_id)
    if not base or not base.raw_text:
        raise HTTPException(status_code=404, detail="Resume not found or has no parsed text")

    # Resolve job description and context from the selected mode
    job_description = ""
    job_title = ""
    company = ""
    linked_job_id = None

    if payload.mode == "job" and payload.job_id:
        job = await JobDocument.get(payload.job_id)
        if job:
            job_description = job.description or ""
            if not job_description.strip():
                # Build a synthetic description from job fields
                parts = [f"Role: {job.title} at {job.company}", f"Location: {job.location}" if job.location else "", f"Remote: yes" if job.remote else ""]
                if job.extracted_keywords:
                    parts.append(f"Key skills: {', '.join(job.extracted_keywords[:15])}")
                if job.tags:
                    parts.append(f"Tags: {', '.join(job.tags)}")
                job_description = ". ".join(p for p in parts if p)
            job_title = job.title
            company = job.company
            linked_job_id = payload.job_id

    elif payload.mode == "keywords" and payload.keywords:
        kw_list = [k.strip() for k in payload.keywords.split(",") if k.strip()]
        job_description = (
            f"The candidate is targeting roles requiring expertise in: {', '.join(kw_list)}. "
            f"Emphasize these technologies and skills throughout the resume."
        )
        job_title = payload.job_title or "Targeted Role"
        company = payload.company or ""

    else:  # "description" mode
        job_description = payload.job_description or ""
        job_title = payload.job_title or ""
        company = payload.company or ""

    if not job_description.strip():
        raise HTTPException(status_code=400, detail="Job description, job ID, or keywords are required")

    # 1. Extract keywords from job description
    job_keywords = await extract_keywords_from_job(job_description)

    # 2. Find missing keywords
    resume_lower = base.raw_text.lower()
    missing = [kw for kw in job_keywords if kw.lower() not in resume_lower]

    # 3. Generate tailored resume
    tailored_text = await generate_tailored_resume(
        base_resume_text=base.raw_text,
        job_description=job_description,
        missing_keywords=missing,
    )

    # 4. Generate a descriptive label for this tailored version
    label = await generate_tailored_label(job_description, job_keywords, job_title)

    # 5. Save as new version
    version = await ResumeDocument.find(
        ResumeDocument.parent_resume_id == payload.resume_id,
    ).count() + 1

    filename = f"tailored_{base.original_filename}"
    if company or job_title:
        filename = f"{job_title or 'tailored'}_{company or ''}_{base.original_filename}"

    tailored = ResumeDocument(
        user_id=user_id,
        original_filename=filename,
        s3_key=f"resumes/tailored/{uuid.uuid4().hex}.txt",
        s3_url=None,
        raw_text=tailored_text,
        sections=[],
        parent_resume_id=payload.resume_id,
        tailored_for_job_id=linked_job_id,
        tailored_label=label,
        version=version,
        tags=base.tags,
    )
    await tailored.insert()

    return TailorResponse(
        tailored_resume_id=str(tailored.id),
        tailored_text=tailored_text,
        tailored_label=label,
        missing_keywords=missing,
        improvements=[
            f"Incorporate '{kw}' — this keyword is missing from your resume."
            for kw in missing[:8]
        ],
    )


# ── MATCH SCORE ───────────────────────────────────
@router.post("/match-score", response_model=MatchScoreResponse)
async def get_match_score(payload: MatchScoreRequest):
    resume = await ResumeDocument.get(payload.resume_id)
    if not resume or not resume.raw_text:
        raise HTTPException(status_code=404, detail="Resume not found or has no parsed text")

    keywords = await extract_keywords_from_job(payload.job_description)
    score, explanation = await compute_match_score(
        resume_text=resume.raw_text,
        job_description=payload.job_description,
        job_keywords=keywords,
    )
    return MatchScoreResponse(score=score, explanation=explanation, keywords=keywords)


# ── INTERVIEW QUESTIONS ───────────────────────────
@router.post("/interview-questions", response_model=InterviewQuestionsResponse)
async def get_interview_questions(payload: InterviewQuestionsRequest):
    questions = await generate_interview_questions(
        job_description=payload.job_description,
        role=payload.role,
    )
    return InterviewQuestionsResponse(
        behavioral=questions.get("behavioral", []),
        technical=questions.get("technical", []),
        role_specific=questions.get("role_specific", []),
    )
