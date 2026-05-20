"""Resume/job embedding similarity scoring."""

import math

from pydantic import BaseModel

from app.models.job_chunk import JobChunkDocument
from app.models.resume import ResumeDocument
from app.models.resume_chunk import ResumeChunkDocument


class ResumeMatchScore(BaseModel):
    resume_id: str
    resume_filename: str
    match_score: float | None = None
    match_explanation: str | None = None


async def score_resume_for_job(job_id: str, resume_id: str, org_id: str) -> ResumeMatchScore | None:
    resume = await ResumeDocument.get(resume_id)
    if not resume or resume.org_id != org_id:
        return None

    score = await calculate_match_score(job_id, resume_id, org_id)
    return ResumeMatchScore(
        resume_id=str(resume.id),
        resume_filename=resume.original_filename,
        match_score=score,
        match_explanation=_explain_score(score),
    )


async def score_resumes_for_job(
    job_id: str,
    resumes: list[ResumeDocument],
    org_id: str,
) -> list[ResumeMatchScore]:
    results = []
    for resume in resumes:
        score = await calculate_match_score(job_id, str(resume.id), org_id)
        results.append(
            ResumeMatchScore(
                resume_id=str(resume.id),
                resume_filename=resume.original_filename,
                match_score=score,
                match_explanation=_explain_score(score),
            )
        )
    return results


async def calculate_match_score(job_id: str, resume_id: str, org_id: str) -> float | None:
    job_chunks = await JobChunkDocument.find({
        "job_id": job_id,
    }).to_list()
    resume_chunks = await ResumeChunkDocument.find({
        "resume_id": resume_id,
        "org_id": org_id,
    }).to_list()
    if not job_chunks or not resume_chunks:
        return None

    best_scores = []
    for job_chunk in job_chunks:
        similarities = [
            _cosine_similarity(job_chunk.embedding, resume_chunk.embedding)
            for resume_chunk in resume_chunks
        ]
        best_scores.append(max(similarities))

    if not best_scores:
        return None

    normalized = (sum(best_scores) / len(best_scores) + 1) / 2
    return round(max(0, min(100, normalized * 100)), 1)


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0

    dot_product = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot_product / (left_norm * right_norm)


def _explain_score(score: float | None) -> str | None:
    if score is None:
        return "Match score unavailable because job or resume embeddings are not ready."
    return "Embedding similarity score based on the closest resume sections for this job."
