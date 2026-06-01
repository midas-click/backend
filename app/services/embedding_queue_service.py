"""Queue embedding jobs without blocking API requests."""

import logging
from datetime import UTC, datetime
from typing import Literal

from app.config import settings
from app.models.job import JobDocument
from app.models.resume import ResumeDocument

logger = logging.getLogger(__name__)

EmbeddingOwner = ResumeDocument | JobDocument
EmbeddingStatus = Literal["disabled", "pending", "processing", "completed", "failed"]


async def enqueue_resume_embedding(resume: ResumeDocument) -> bool:
    return await _enqueue_embedding(
        owner=resume,
        task_path="app.worker.embedding_tasks",
        task_name="embed_resume_task",
        owner_name="resume",
    )


async def enqueue_job_embedding(job: JobDocument, source_text: str | None = None) -> bool:
    return await _enqueue_embedding(
        owner=job,
        task_path="app.worker.embedding_tasks",
        task_name="embed_job_task",
        owner_name="job",
        source_text=source_text,
    )


async def mark_embedding_status(
    owner: EmbeddingOwner,
    status: EmbeddingStatus,
    error: str | None = None,
) -> EmbeddingOwner:
    owner.embedding_status = status
    owner.embedding_error = error
    if status == "completed":
        owner.embedded_at = datetime.now(UTC)
    elif status in {"pending", "processing", "failed", "disabled"}:
        owner.embedded_at = None
    return await owner.save()


async def _enqueue_embedding(
    owner: EmbeddingOwner,
    task_path: str,
    task_name: str,
    owner_name: str,
    source_text: str | None = None,
) -> bool:
    if not settings.EMBEDDINGS_ENABLED:
        await mark_embedding_status(owner, "disabled")
        return False

    await mark_embedding_status(owner, "pending")

    if not settings.EMBEDDINGS_ASYNC_ENABLED:
        await _run_embedding_inline(owner, owner_name, source_text)
        return False

    try:
        module = __import__(task_path, fromlist=[task_name])
        task = getattr(module, task_name)
        if owner_name == "job":
            task.delay(str(owner.id), source_text)
        else:
            task.delay(str(owner.id))
        return True
    except Exception as exc:
        logger.exception("Failed to enqueue %s embedding for id=%s", owner_name, owner.id)
        await mark_embedding_status(owner, "failed", f"Failed to queue embedding job: {exc}")
        return False


async def _run_embedding_inline(
    owner: EmbeddingOwner,
    owner_name: str,
    source_text: str | None = None,
) -> None:
    logger.info("Embedding async queue disabled; running inline for %s_id=%s", owner_name, owner.id)
    await mark_embedding_status(owner, "processing")
    try:
        if owner_name == "resume":
            from app.services.resume_chunk_service import replace_resume_chunks

            chunks = await replace_resume_chunks(owner, owner.sections)
            owner.vector_store = settings.VECTOR_STORE
            owner.vector_chunk_count = len(chunks)
        else:
            from app.services.job_chunk_service import replace_job_chunks

            chunks = await replace_job_chunks(owner, source_text)
            owner.vector_store = settings.VECTOR_STORE
            owner.vector_chunk_count = len(chunks)
        await mark_embedding_status(owner, "completed")
    except Exception as exc:
        logger.exception("Inline %s embedding failed for id=%s", owner_name, owner.id)
        await mark_embedding_status(owner, "failed", str(exc))
