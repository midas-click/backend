"""Resume/job embedding similarity scoring."""

from dataclasses import dataclass

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


@dataclass(frozen=True)
class MatchScoreCalculation:
    score: float | None
    explanation: str | None


async def score_resume_for_job(job_id: str, resume_id: str, org_id: str) -> ResumeMatchScore | None:
    resume = await ResumeDocument.get(resume_id)
    if not resume or resume.org_id != org_id:
        return None

    calculation = await calculate_match_score_detail(job_id, resume_id, org_id, resume=resume)
    return ResumeMatchScore(
        resume_id=str(resume.id),
        resume_filename=resume.original_filename,
        match_score=calculation.score,
        match_explanation=calculation.explanation,
    )


async def score_resumes_for_job(
    job_id: str,
    resumes: list[ResumeDocument],
    org_id: str,
) -> list[ResumeMatchScore]:
    results = []
    for resume in resumes:
        calculation = await calculate_match_score_detail(job_id, str(resume.id), org_id, resume=resume)
        results.append(
            ResumeMatchScore(
                resume_id=str(resume.id),
                resume_filename=resume.original_filename,
                match_score=calculation.score,
                match_explanation=calculation.explanation,
            )
        )
    return results


async def calculate_match_score(job_id: str, resume_id: str, org_id: str) -> float | None:
    return (await calculate_match_score_detail(job_id, resume_id, org_id)).score


async def calculate_match_score_detail(
    job_id: str,
    resume_id: str,
    org_id: str,
    resume: ResumeDocument | None = None,
) -> MatchScoreCalculation:
    job = await JobDocument.get(job_id)
    if not job:
        return MatchScoreCalculation(None, "Job was not found, so match score cannot be calculated.")

    if not _is_embedding_ready(job):
        return MatchScoreCalculation(None, _embedding_not_ready_message("Job", job))

    if resume is None:
        resume = await ResumeDocument.get(resume_id)
    if not resume or resume.org_id != org_id:
        return MatchScoreCalculation(None, "Resume was not found, so match score cannot be calculated.")

    if not _is_embedding_ready(resume):
        return MatchScoreCalculation(None, _embedding_not_ready_message("Resume", resume))

    job_vectors = await fetch_job_vectors(job)
    if not job_vectors:
        return MatchScoreCalculation(None, "Job embedding is marked completed, but no job vectors were found.")

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
        return MatchScoreCalculation(None, "Resume embedding is marked completed, but no resume vectors were found.")

    normalized = (sum(best_scores) / len(best_scores) + 1) / 2
    score = round(max(0, min(100, normalized * 100)), 1)
    return MatchScoreCalculation(score, _explain_score(score))


def _explain_score(score: float | None) -> str | None:
    if score is None:
        return "Match score unavailable because job or resume embeddings are not ready."
    if settings.VECTOR_STORE == "pinecone":
        return "Pinecone vector similarity score based on the closest resume sections for this job."
    return "Embedding similarity score based on the closest resume sections for this job."


def _is_embedding_ready(owner: JobDocument | ResumeDocument) -> bool:
    return (
        getattr(owner, "embedding_status", None) == "completed"
        and (getattr(owner, "vector_chunk_count", 0) or 0) > 0
    )


def _embedding_not_ready_message(owner_name: str, owner: JobDocument | ResumeDocument) -> str:
    status = getattr(owner, "embedding_status", None) or "unknown"
    error = getattr(owner, "embedding_error", None)
    chunk_count = getattr(owner, "vector_chunk_count", 0) or 0

    if status in {"pending", "processing"}:
        return f"{owner_name} embedding is still {status}; match score will be available after embedding completes."
    if status == "failed":
        if error:
            return f"{owner_name} embedding failed: {error}"
        return f"{owner_name} embedding failed, so match score cannot be calculated."
    if status == "disabled":
        return f"{owner_name} embedding is disabled, so match score cannot be calculated."
    if status == "completed" and chunk_count <= 0:
        return f"{owner_name} embedding completed, but no vector chunks were stored."
    return f"{owner_name} embedding is not ready yet; current status is {status}."
