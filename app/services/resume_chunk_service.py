"""Chunk resumes and persist embeddings in the configured vector store."""

from app.models.resume import ResumeDocument, ResumeSection
from app.services.vector_store_service import (
    StoredVector,
    TextChunk,
    chunk_resume_sections,
    delete_resume_vectors,
    upsert_resume_chunks,
)


class ResumeChunkServiceError(RuntimeError):
    pass


ResumeTextChunk = TextChunk


async def replace_resume_chunks(
    resume: ResumeDocument,
    sections: list[ResumeSection],
) -> list[StoredVector]:
    try:
        return await upsert_resume_chunks(resume, sections)
    except Exception as exc:
        raise ResumeChunkServiceError(str(exc)) from exc


async def delete_resume_chunks(resume: ResumeDocument) -> None:
    await delete_resume_vectors(resume)
