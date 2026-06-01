"""Pinecone-backed vector storage for job and resume chunks."""

from dataclasses import dataclass
from typing import Any

import asyncio

from app.config import settings
from app.models.job import JobDocument
from app.models.resume import ResumeDocument, ResumeSection
from app.services.embedding_service import generate_embeddings


class VectorStoreError(RuntimeError):
    pass


@dataclass(frozen=True)
class TextChunk:
    chunk_index: int
    content: str
    section_title: str | None = None


@dataclass(frozen=True)
class StoredVector:
    id: str
    values: list[float]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class VectorMatch:
    id: str
    score: float
    metadata: dict[str, Any]


_index: Any | None = None
JOB_VECTOR_NAMESPACE = "jobs"


def job_vector_id(job_id: str, chunk_index: int) -> str:
    return f"job:{job_id}:{chunk_index}"


def resume_vector_id(resume_id: str, chunk_index: int) -> str:
    return f"resume:{resume_id}:{chunk_index}"


def chunk_job(job: JobDocument, source_text: str | None = None, max_chars: int | None = None) -> list[TextChunk]:
    text = _job_text(job, source_text)
    return [
        TextChunk(chunk_index=index, content=content)
        for index, content in enumerate(_split_text(text, max_chars or settings.RESUME_CHUNK_MAX_CHARS))
    ]


def chunk_resume_sections(
    sections: list[ResumeSection],
    max_chars: int | None = None,
) -> list[TextChunk]:
    limit = max_chars or settings.RESUME_CHUNK_MAX_CHARS
    chunks: list[TextChunk] = []
    for section in sections:
        section_title = (section.title or "Resume").strip() or "Resume"
        for content in _split_text(section.content, limit):
            chunks.append(TextChunk(
                chunk_index=len(chunks),
                content=content,
                section_title=section_title,
            ))
    return chunks


async def upsert_job_chunks(job: JobDocument, source_text: str | None = None) -> list[StoredVector]:
    chunks = chunk_job(job, source_text)
    if not chunks:
        raise VectorStoreError("Job did not contain any text chunks to embed")

    embeddings = await generate_embeddings([chunk.content for chunk in chunks])
    vectors = [
        StoredVector(
            id=job_vector_id(str(job.id), chunk.chunk_index),
            values=embedding,
            metadata={
                "kind": "job",
                "job_id": str(job.id),
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
                "embedding_model": settings.EMBEDDING_MODEL,
                "embedding_dimensions": settings.EMBEDDING_DIMENSIONS,
            },
        )
        for chunk, embedding in zip(chunks, embeddings, strict=True)
    ]
    await delete_job_vectors(job)
    await _upsert_vectors(JOB_VECTOR_NAMESPACE, vectors)
    return vectors


async def upsert_resume_chunks(
    resume: ResumeDocument,
    sections: list[ResumeSection],
) -> list[StoredVector]:
    chunks = chunk_resume_sections(sections)
    if not chunks:
        raise VectorStoreError("Resume did not contain any text chunks to embed")

    embeddings = await generate_embeddings([chunk.content for chunk in chunks])
    vectors = [
        StoredVector(
            id=resume_vector_id(str(resume.id), chunk.chunk_index),
            values=embedding,
            metadata={
                "kind": "resume",
                "resume_id": str(resume.id),
                "user_id": resume.user_id,
                "org_id": resume.org_id,
                "profile_id": resume.profile_id or "",
                "section_title": chunk.section_title or "Resume",
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
                "embedding_model": settings.EMBEDDING_MODEL,
                "embedding_dimensions": settings.EMBEDDING_DIMENSIONS,
            },
        )
        for chunk, embedding in zip(chunks, embeddings, strict=True)
    ]
    await delete_resume_vectors(resume)
    await _upsert_vectors(resume.org_id, vectors)
    return vectors


async def delete_job_vectors(job: JobDocument) -> None:
    await delete_job_vectors_by_id(
        job_id=str(job.id),
        vector_chunk_count=getattr(job, "vector_chunk_count", 0) or 0,
    )


async def delete_resume_vectors(resume: ResumeDocument) -> None:
    await delete_resume_vectors_by_id(
        org_id=resume.org_id,
        resume_id=str(resume.id),
        vector_chunk_count=getattr(resume, "vector_chunk_count", 0) or 0,
    )


async def delete_job_vectors_by_id(job_id: str, vector_chunk_count: int) -> None:
    ids = [job_vector_id(job_id, index) for index in range(vector_chunk_count or 0)]
    if ids:
        await _delete_vectors(JOB_VECTOR_NAMESPACE, ids)


async def delete_resume_vectors_by_id(org_id: str, resume_id: str, vector_chunk_count: int) -> None:
    ids = [
        resume_vector_id(resume_id, index)
        for index in range(vector_chunk_count or 0)
    ]
    if ids:
        await _delete_vectors(org_id, ids)


async def fetch_job_vectors(job: JobDocument) -> list[StoredVector]:
    ids = [job_vector_id(str(job.id), index) for index in range(getattr(job, "vector_chunk_count", 0) or 0)]
    if not ids:
        return []

    try:
        response = await asyncio.to_thread(_get_index().fetch, ids=ids, namespace=JOB_VECTOR_NAMESPACE)
    except Exception as exc:
        if _is_namespace_not_found(exc):
            return []
        raise
    vectors = _response_vectors(response)
    return [
        StoredVector(
            id=vector_id,
            values=list(_vector_get(item, "values") or []),
            metadata=dict(_vector_get(item, "metadata") or {}),
        )
        for vector_id, item in vectors.items()
        if _vector_get(item, "values")
    ]


async def query_resume_chunks(
    org_id: str,
    profile_id: str | None,
    job_vector: list[float],
    top_k: int | None = None,
    resume_id: str | None = None,
) -> list[VectorMatch]:
    filters: dict[str, Any] = {"kind": {"$eq": "resume"}}
    if profile_id:
        filters["profile_id"] = {"$eq": profile_id}
    if resume_id:
        filters["resume_id"] = {"$eq": resume_id}

    try:
        response = await asyncio.to_thread(
            _get_index().query,
            vector=job_vector,
            namespace=org_id,
            filter=filters,
            top_k=top_k or settings.PINECONE_TOP_K,
            include_metadata=True,
        )
    except Exception as exc:
        if _is_namespace_not_found(exc):
            return []
        raise
    return [
        VectorMatch(
            id=str(_match_get(match, "id")),
            score=float(_match_get(match, "score") or 0.0),
            metadata=dict(_match_get(match, "metadata") or {}),
        )
        for match in _response_matches(response)
    ]


async def _upsert_vectors(namespace: str, vectors: list[StoredVector]) -> None:
    records = [
        {
            "id": vector.id,
            "values": vector.values,
            "metadata": vector.metadata,
        }
        for vector in vectors
    ]
    await asyncio.to_thread(_get_index().upsert, vectors=records, namespace=namespace)


async def _delete_vectors(namespace: str, ids: list[str]) -> None:
    try:
        await asyncio.to_thread(_get_index().delete, ids=ids, namespace=namespace)
    except Exception as exc:
        if _is_namespace_not_found(exc):
            return
        raise


def _get_index() -> Any:
    global _index
    if _index is not None:
        return _index
    if not settings.PINECONE_API_KEY:
        raise VectorStoreError("PINECONE_API_KEY is not configured")
    try:
        from pinecone import Pinecone, ServerlessSpec
    except Exception as exc:
        raise VectorStoreError("Install pinecone to use the Pinecone vector store") from exc

    client = Pinecone(api_key=settings.PINECONE_API_KEY)
    existing_indexes = _index_names(client.list_indexes())
    if settings.PINECONE_INDEX_NAME not in existing_indexes:
        client.create_index(
            name=settings.PINECONE_INDEX_NAME,
            dimension=settings.EMBEDDING_DIMENSIONS,
            metric="cosine",
            spec=ServerlessSpec(cloud=settings.PINECONE_CLOUD, region=settings.PINECONE_REGION),
        )
    _index = client.Index(settings.PINECONE_INDEX_NAME)
    return _index


def _index_names(indexes: Any) -> set[str]:
    if hasattr(indexes, "names"):
        return set(indexes.names())
    names = set()
    for item in indexes:
        if isinstance(item, dict):
            names.add(str(item.get("name")))
        elif hasattr(item, "name"):
            names.add(str(item.name))
        else:
            names.add(str(item))
    return {name for name in names if name}


def _is_namespace_not_found(exc: Exception) -> bool:
    text = str(exc).lower()
    return "namespace not found" in text


def _job_text(job: JobDocument, source_text: str | None = None) -> str:
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
    if source_text:
        parts.append(f"Job text:\n{source_text}")
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


def _response_vectors(response: Any) -> dict[str, Any]:
    if isinstance(response, dict):
        return response.get("vectors", {})
    return dict(getattr(response, "vectors", {}) or {})


def _response_matches(response: Any) -> list[Any]:
    if isinstance(response, dict):
        return list(response.get("matches", []))
    return list(getattr(response, "matches", []) or [])


def _match_get(match: Any, key: str) -> Any:
    if isinstance(match, dict):
        return match.get(key)
    return getattr(match, key, None)


def _vector_get(vector: Any, key: str) -> Any:
    if isinstance(vector, dict):
        return vector.get(key)
    return getattr(vector, key, None)
