from types import SimpleNamespace

import pytest

from app.models.resume import ResumeSection
from app.services import vector_store_service
from app.services.vector_store_service import (
    job_vector_id,
    resume_vector_id,
    upsert_job_chunks,
    upsert_resume_chunks,
)


def test_vector_ids_are_deterministic():
    assert job_vector_id("job_1", 2) == "job:job_1:2"
    assert resume_vector_id("resume_1", 3) == "resume:resume_1:3"


@pytest.mark.asyncio
async def test_upsert_job_chunks_writes_required_metadata(monkeypatch):
    upserts = []
    deletes = []

    monkeypatch.setattr(vector_store_service, "generate_embeddings", lambda texts: _async_value([[1.0, 0.0] for _ in texts]))
    monkeypatch.setattr(vector_store_service, "_upsert_vectors", lambda namespace, vectors: _async_append(upserts, (namespace, vectors)))
    monkeypatch.setattr(vector_store_service, "_delete_vectors", lambda namespace, ids: _async_append(deletes, (namespace, ids)))
    monkeypatch.setattr(vector_store_service.settings, "EMBEDDING_MODEL", "test-model")
    monkeypatch.setattr(vector_store_service.settings, "EMBEDDING_DIMENSIONS", 2)

    job = SimpleNamespace(
        id="job_1",
        user_id="user_1",
        org_id="org_1",
        title="Backend Engineer",
        company="Midas",
        location=None,
        salary_range=None,
        tags=[],
        vector_chunk_count=1,
    )

    vectors = await upsert_job_chunks(job, "Build APIs")

    assert deletes == [("org_1", ["job:job_1:0"])]
    assert upserts[0][0] == "org_1"
    assert vectors[0].id == "job:job_1:0"
    assert vectors[0].metadata["kind"] == "job"
    assert vectors[0].metadata["job_id"] == "job_1"
    assert vectors[0].metadata["content"]


@pytest.mark.asyncio
async def test_upsert_resume_chunks_writes_required_metadata(monkeypatch):
    upserts = []
    monkeypatch.setattr(vector_store_service, "generate_embeddings", lambda texts: _async_value([[0.0, 1.0] for _ in texts]))
    monkeypatch.setattr(vector_store_service, "_upsert_vectors", lambda namespace, vectors: _async_append(upserts, (namespace, vectors)))
    monkeypatch.setattr(vector_store_service, "_delete_vectors", lambda namespace, ids: _async_value(None))
    monkeypatch.setattr(vector_store_service.settings, "EMBEDDING_MODEL", "test-model")
    monkeypatch.setattr(vector_store_service.settings, "EMBEDDING_DIMENSIONS", 2)

    resume = SimpleNamespace(
        id="resume_1",
        user_id="user_1",
        org_id="org_1",
        profile_id="profile_1",
        vector_chunk_count=0,
    )

    vectors = await upsert_resume_chunks(resume, [ResumeSection(title="Skills", content="Python")])

    assert upserts[0][0] == "org_1"
    assert vectors[0].id == "resume:resume_1:0"
    assert vectors[0].metadata["kind"] == "resume"
    assert vectors[0].metadata["resume_id"] == "resume_1"
    assert vectors[0].metadata["profile_id"] == "profile_1"
    assert vectors[0].metadata["content"] == "Python"


async def _async_value(value):
    return value


async def _async_append(items, value):
    items.append(value)
    return None
