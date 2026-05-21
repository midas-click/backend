"""Chunk saved jobs and persist local BGE embeddings for match scoring."""

from dataclasses import dataclass

from app.config import settings
from app.models.job import JobDocument
from app.models.job_chunk import JobChunkDocument
from app.services.embedding_service import generate_embeddings


class JobChunkServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class JobTextChunk:
    chunk_index: int
    content: str


def chunk_job(job: JobDocument, max_chars: int | None = None) -> list[JobTextChunk]:
    text = _job_text(job)
    chunks = _split_text(text, max_chars or settings.RESUME_CHUNK_MAX_CHARS)
    return [JobTextChunk(chunk_index=index, content=content) for index, content in enumerate(chunks)]


async def replace_job_chunks(job: JobDocument) -> list[JobChunkDocument]:
    chunks = chunk_job(job)
    if not chunks:
        raise JobChunkServiceError("Job did not contain any text chunks to embed")

    try:
        embeddings = await generate_embeddings([chunk.content for chunk in chunks])
    except Exception as exc:
        raise JobChunkServiceError(str(exc)) from exc

    documents = [
        JobChunkDocument(
            job_id=str(job.id),
            user_id=job.user_id,
            org_id=job.org_id,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            embedding=embedding,
            embedding_model=settings.EMBEDDING_MODEL,
            embedding_dimensions=settings.EMBEDDING_DIMENSIONS,
        )
        for chunk, embedding in zip(chunks, embeddings, strict=True)
    ]

    await JobChunkDocument.find(JobChunkDocument.job_id == str(job.id)).delete()
    await _insert_documents(documents)
    return documents


async def delete_job_chunks(job_id: str) -> None:
    await JobChunkDocument.find(JobChunkDocument.job_id == job_id).delete()


def _job_text(job: JobDocument) -> str:
    parts = [
        f"Title: {job.title}",
        f"Company: {job.company}",
    ]
    if job.location:
        parts.append(f"Location: {job.location}")
    if job.salary_range:
        parts.append(f"Salary: {job.salary_range}")
    if job.tags:
        parts.append(f"Tags: {', '.join(job.tags)}")
    if job.description:
        parts.append(f"Description:\n{job.description}")
    return "\n\n".join(parts)


def _split_text(text: str, max_chars: int) -> list[str]:
    clean_text = "\n".join(line.strip() for line in text.splitlines()).strip()
    if not clean_text:
        return []
    if len(clean_text) <= max_chars:
        return [clean_text]

    chunks: list[str] = []
    current = ""
    for paragraph in [part.strip() for part in clean_text.split("\n") if part.strip()]:
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_text(paragraph, max_chars))
            continue

        separator = "\n" if current else ""
        candidate = f"{current}{separator}{paragraph}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = paragraph

    if current:
        chunks.append(current)
    return chunks


def _split_long_text(text: str, max_chars: int) -> list[str]:
    return [text[start:start + max_chars].strip() for start in range(0, len(text), max_chars)]


async def _insert_documents(documents: list[JobChunkDocument]) -> None:
    if hasattr(JobChunkDocument, "insert_many"):
        await JobChunkDocument.insert_many(documents)
        return

    for document in documents:
        await document.insert()
