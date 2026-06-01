"""Chunk jobs and persist embeddings in the configured vector store."""

from app.models.job import JobDocument
from app.services.vector_store_service import (
    StoredVector,
    TextChunk,
    chunk_job,
    delete_job_vectors,
    upsert_job_chunks,
)


class JobChunkServiceError(RuntimeError):
    pass


JobTextChunk = TextChunk


async def replace_job_chunks(job: JobDocument, source_text: str | None = None) -> list[StoredVector]:
    try:
        return await upsert_job_chunks(job, source_text)
    except Exception as exc:
        raise JobChunkServiceError(str(exc)) from exc


async def delete_job_chunks(job: JobDocument) -> None:
    await delete_job_vectors(job)
