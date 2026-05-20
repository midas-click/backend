from types import SimpleNamespace

import pytest

from app.services import job_chunk_service
from app.services.job_chunk_service import chunk_job, replace_job_chunks


def test_chunk_job_includes_core_job_fields():
    job = SimpleNamespace(
        title="Backend Engineer",
        company="Midas",
        location="Remote",
        salary_range="$100k-$120k",
        tags=["python", "mongodb"],
        description="Build APIs",
    )

    chunks = chunk_job(job, max_chars=1000)

    assert len(chunks) == 1
    assert "Title: Backend Engineer" in chunks[0].content
    assert "Tags: python, mongodb" in chunks[0].content
    assert "Description:\nBuild APIs" in chunks[0].content


@pytest.mark.asyncio
async def test_replace_job_chunks_builds_documents(monkeypatch):
    inserted = []
    deleted = []

    async def fake_generate_embeddings(texts):
        return [[1.0, 0.0, 0.0] for _ in texts]

    class FakeFind:
        async def delete(self):
            deleted.append("deleted")

    class FakeJobChunkDocument:
        job_id = "job_id"

        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

        @classmethod
        def find(cls, *args):
            return FakeFind()

        async def insert(self):
            inserted.append(self)
            return self

    monkeypatch.setattr(job_chunk_service, "generate_embeddings", fake_generate_embeddings)
    monkeypatch.setattr(job_chunk_service, "JobChunkDocument", FakeJobChunkDocument)
    monkeypatch.setattr(job_chunk_service.settings, "EMBEDDING_MODEL", "test-model")
    monkeypatch.setattr(job_chunk_service.settings, "EMBEDDING_DIMENSIONS", 3)

    job = SimpleNamespace(
        id="job_1",
        user_id="user_1",
        org_id="org_1",
        title="Backend Engineer",
        company="Midas",
        location=None,
        salary_range=None,
        tags=[],
        description="Build APIs",
    )

    docs = await replace_job_chunks(job)

    assert deleted == ["deleted"]
    assert docs == inserted
    assert docs[0].job_id == "job_1"
    assert docs[0].org_id == "org_1"
    assert docs[0].embedding == [1.0, 0.0, 0.0]
