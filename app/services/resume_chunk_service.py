"""Chunk parsed resumes and persist OpenAI embeddings for vector search."""

from dataclasses import dataclass

from app.config import settings
from app.models.resume import ResumeDocument, ResumeSection
from app.models.resume_chunk import ResumeChunkDocument
from app.services.embedding_service import generate_embeddings


class ResumeChunkServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class ResumeTextChunk:
    section_title: str
    chunk_index: int
    content: str


def chunk_resume_sections(
    sections: list[ResumeSection],
    max_chars: int | None = None,
) -> list[ResumeTextChunk]:
    limit = max_chars or settings.RESUME_CHUNK_MAX_CHARS
    chunks: list[ResumeTextChunk] = []

    for section in sections:
        section_title = (section.title or "Resume").strip() or "Resume"
        for content in _split_text(section.content, limit):
            chunks.append(
                ResumeTextChunk(
                    section_title=section_title,
                    chunk_index=len(chunks),
                    content=content,
                )
            )

    return chunks


async def replace_resume_chunks(
    resume: ResumeDocument,
    sections: list[ResumeSection],
) -> list[ResumeChunkDocument]:
    chunks = chunk_resume_sections(sections)
    if not chunks:
        raise ResumeChunkServiceError("Resume did not contain any text chunks to embed")

    embeddings = await generate_embeddings([chunk.content for chunk in chunks])
    documents = [
        ResumeChunkDocument(
            resume_id=str(resume.id),
            user_id=resume.user_id,
            org_id=resume.org_id,
            profile_id=resume.profile_id,
            section_title=chunk.section_title,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            embedding=embedding,
            embedding_model=settings.EMBEDDING_MODEL,
            embedding_dimensions=settings.EMBEDDING_DIMENSIONS,
        )
        for chunk, embedding in zip(chunks, embeddings, strict=True)
    ]

    await ResumeChunkDocument.find(ResumeChunkDocument.resume_id == str(resume.id)).delete()
    await _insert_documents(documents)
    return documents


async def delete_resume_chunks(resume_id: str) -> None:
    await ResumeChunkDocument.find(ResumeChunkDocument.resume_id == resume_id).delete()


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


async def _insert_documents(documents: list[ResumeChunkDocument]) -> None:
    if hasattr(ResumeChunkDocument, "insert_many"):
        await ResumeChunkDocument.insert_many(documents)
        return

    for document in documents:
        await document.insert()
