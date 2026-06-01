"""Queue vector cleanup without blocking delete API responses."""

import logging

from fastapi import BackgroundTasks

from app.config import settings
from app.models.job import JobDocument
from app.models.resume import ResumeDocument
from app.services.vector_store_service import delete_job_vectors_by_id, delete_resume_vectors_by_id

logger = logging.getLogger(__name__)


def enqueue_job_vector_cleanup(job: JobDocument, background_tasks: BackgroundTasks) -> None:
    job_id = str(job.id)
    vector_chunk_count = job.vector_chunk_count or 0
    if vector_chunk_count <= 0:
        return

    background_tasks.add_task(_dispatch_job_vector_cleanup, job_id, vector_chunk_count)


def enqueue_resume_vector_cleanup(resume: ResumeDocument, background_tasks: BackgroundTasks) -> None:
    org_id = resume.org_id
    resume_id = str(resume.id)
    vector_chunk_count = resume.vector_chunk_count or 0
    if vector_chunk_count <= 0:
        return

    background_tasks.add_task(_dispatch_resume_vector_cleanup, org_id, resume_id, vector_chunk_count)


async def _dispatch_job_vector_cleanup(job_id: str, vector_chunk_count: int) -> None:
    if settings.EMBEDDINGS_ASYNC_ENABLED:
        if _try_enqueue_celery_cleanup("delete_job_vectors_task", job_id, vector_chunk_count):
            return

    logger.info("Running job vector cleanup as FastAPI background task id=%s", job_id)
    await delete_job_vectors_by_id(job_id, vector_chunk_count)


async def _dispatch_resume_vector_cleanup(org_id: str, resume_id: str, vector_chunk_count: int) -> None:
    if settings.EMBEDDINGS_ASYNC_ENABLED:
        if _try_enqueue_celery_cleanup("delete_resume_vectors_task", org_id, resume_id, vector_chunk_count):
            return

    logger.info("Running resume vector cleanup as FastAPI background task id=%s", resume_id)
    await delete_resume_vectors_by_id(org_id, resume_id, vector_chunk_count)


def _try_enqueue_celery_cleanup(task_name: str, *task_args: object) -> bool:
    try:
        module = __import__("app.worker.embedding_tasks", fromlist=[task_name])
        task = getattr(module, task_name)
        task.delay(*task_args)
        return True
    except Exception:
        owner_id = task_args[1] if task_name == "delete_resume_vectors_task" else task_args[0]
        logger.exception("Failed to enqueue vector cleanup task=%s id=%s", task_name, owner_id)
        return False
