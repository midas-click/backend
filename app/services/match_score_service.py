"""Resume/job embedding similarity scoring."""

from pydantic import BaseModel

from app.config import settings
from app.models.job import JobDocument
from app.models.resume import ResumeDocument
from app.services.vector_store_service import fetch_job_vectors, query_resume_chunks


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
    job = await JobDocument.get(job_id)
    if not job or job.org_id != org_id:
        return None

    job_vectors = await fetch_job_vectors(job)
    if not job_vectors:
        return None

    best_scores = []
    for job_vector in job_vectors:
        matches = await query_resume_chunks(
            org_id=org_id,
            profile_id=None,
            job_vector=job_vector.values,
            top_k=1,
            resume_id=resume_id,
        )
        if matches:
            best_scores.append(matches[0].score)

    if not best_scores:
        return None

    normalized = (sum(best_scores) / len(best_scores) + 1) / 2
    return round(max(0, min(100, normalized * 100)), 1)


def _explain_score(score: float | None) -> str | None:
    if score is None:
        return "Match score unavailable because job or resume embeddings are not ready."
    if settings.VECTOR_STORE == "pinecone":
        return "Pinecone vector similarity score based on the closest resume sections for this job."
    return "Embedding similarity score based on the closest resume sections for this job."
