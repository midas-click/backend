from types import SimpleNamespace

import pytest

from app.models.resume import ResumeSection
from app.services import resume_chunk_service
from app.services.resume_chunk_service import chunk_resume_sections, replace_resume_chunks


def test_chunk_resume_sections_skips_empty_sections():
    chunks = chunk_resume_sections([
        ResumeSection(title="Experience", content="   "),
        ResumeSection(title="Skills", content="Python\nFastAPI"),
    ])

    assert len(chunks) == 1
    assert chunks[0].section_title == "Skills"
    assert chunks[0].content == "Python\nFastAPI"


def test_chunk_resume_sections_splits_long_sections():
    chunks = chunk_resume_sections(
        [ResumeSection(title="Experience", content="A" * 12)],
        max_chars=5,
    )

    assert [chunk.content for chunk in chunks] == ["AAAAA", "AAAAA", "AA"]
    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2]


@pytest.mark.asyncio
async def test_replace_resume_chunks_builds_documents(monkeypatch):
    inserted = []
    deleted_filters = []

    async def fake_generate_embeddings(texts):
        return [[float(index), 0.0, 1.0] for index, _ in enumerate(texts)]

    class FakeFind:
        async def delete(self):
            deleted_filters.append("deleted")

    class FakeResumeChunkDocument:
        resume_id = "resume_id"

        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

        @classmethod
        def find(cls, *args):
            return FakeFind()

        async def insert(self):
            inserted.append(self)
            return self

    monkeypatch.setattr(resume_chunk_service, "generate_embeddings", fake_generate_embeddings)
    monkeypatch.setattr(resume_chunk_service, "ResumeChunkDocument", FakeResumeChunkDocument)
    monkeypatch.setattr(resume_chunk_service.settings, "EMBEDDING_MODEL", "test-model")
    monkeypatch.setattr(resume_chunk_service.settings, "EMBEDDING_DIMENSIONS", 3)

    resume = SimpleNamespace(
        id="resume_1",
        user_id="user_1",
        org_id="org_1",
        profile_id="profile_1",
    )

    docs = await replace_resume_chunks(
        resume,
        [ResumeSection(title="Experience", content="Built APIs")],
    )

    assert deleted_filters == ["deleted"]
    assert docs == inserted
    assert docs[0].resume_id == "resume_1"
    assert docs[0].org_id == "org_1"
    assert docs[0].profile_id == "profile_1"
    assert docs[0].section_title == "Experience"
    assert docs[0].embedding == [0.0, 0.0, 1.0]
