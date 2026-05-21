"""Celery tasks that generate resume and job embeddings."""

import asyncio
import logging
from typing import Awaitable

from celery.exceptions import Retry

from app.db.mongodb import close_mongo_connection, connect_to_mongo
from app.models.job import JobDocument
from app.models.resume import ResumeDocument
from app.services.embedding_queue_service import mark_embedding_status
from app.services.job_chunk_service import replace_job_chunks
from app.services.resume_chunk_service import replace_resume_chunks
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_RETRY_DELAY_SECONDS = 30


@celery_app.task(bind=True, max_retries=MAX_RETRIES, name="embeddings.resume")
def embed_resume_task(self, resume_id: str) -> dict:
    try:
        return _run_async(_embed_resume(resume_id))
    except Exception as exc:
        _handle_retry_or_failure(self, resume_id, "resume", exc)
        raise


@celery_app.task(bind=True, max_retries=MAX_RETRIES, name="embeddings.job")
def embed_job_task(self, job_id: str) -> dict:
    try:
        return _run_async(_embed_job(job_id))
    except Exception as exc:
        _handle_retry_or_failure(self, job_id, "job", exc)
        raise


async def _embed_resume(resume_id: str) -> dict:
    await connect_to_mongo()
    try:
        resume = await ResumeDocument.get(resume_id)
        if not resume:
            return {"status": "missing", "resume_id": resume_id}

        await mark_embedding_status(resume, "processing")
        chunks = await replace_resume_chunks(resume, resume.sections)
        await mark_embedding_status(resume, "completed")
        return {"status": "completed", "resume_id": resume_id, "chunks": len(chunks)}
    finally:
        await close_mongo_connection()


async def _embed_job(job_id: str) -> dict:
    await connect_to_mongo()
    try:
        job = await JobDocument.get(job_id)
        if not job:
            return {"status": "missing", "job_id": job_id}

        await mark_embedding_status(job, "processing")
        chunks = await replace_job_chunks(job)
        await mark_embedding_status(job, "completed")
        return {"status": "completed", "job_id": job_id, "chunks": len(chunks)}
    finally:
        await close_mongo_connection()


def _handle_retry_or_failure(self, owner_id: str, owner_name: str, exc: Exception) -> None:
    logger.exception("%s embedding task failed for id=%s", owner_name.capitalize(), owner_id)
    if self.request.retries < MAX_RETRIES:
        _try_mark_failed(owner_id, owner_name, f"Retrying after error: {exc}")
        countdown = BASE_RETRY_DELAY_SECONDS * (self.request.retries + 1)
        raise self.retry(exc=exc, countdown=countdown)

    _try_mark_failed(owner_id, owner_name, str(exc))


def _try_mark_failed(owner_id: str, owner_name: str, error: str) -> None:
    try:
        _run_async(_mark_failed(owner_id, owner_name, error))
    except Exception:
        logger.exception("Failed to mark %s embedding as failed for id=%s", owner_name, owner_id)


async def _mark_failed(owner_id: str, owner_name: str, error: str) -> None:
    await connect_to_mongo()
    try:
        if owner_name == "resume":
            owner = await ResumeDocument.get(owner_id)
        else:
            owner = await JobDocument.get(owner_id)
        if owner:
            await mark_embedding_status(owner, "failed", error)
    finally:
        await close_mongo_connection()


def _run_async(awaitable: Awaitable[dict] | Awaitable[None]) -> dict | None:
    try:
        return asyncio.run(awaitable)
    except Retry:
        raise
