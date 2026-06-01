from types import SimpleNamespace

import pytest

from app.models.resume import ResumeSection
from app.services import vector_store_service
from app.services.vector_store_service import (
    delete_resume_vectors_by_id,
    fetch_job_vectors,
    job_vector_id,
    query_resume_chunks,
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
        title="Backend Engineer",
        company="Midas",
        location=None,
        salary_range=None,
        tags=[],
        vector_chunk_count=1,
    )

    vectors = await upsert_job_chunks(job, "Build APIs")

    assert deletes == [("jobs", ["job:job_1:0"])]
    assert upserts[0][0] == "jobs"
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


@pytest.mark.asyncio
async def test_fetch_job_vectors_returns_empty_when_namespace_missing(monkeypatch):
    monkeypatch.setattr(vector_store_service, "_get_index", lambda: FakeIndex())

    job = SimpleNamespace(id="job_1", vector_chunk_count=1)

    assert await fetch_job_vectors(job) == []


@pytest.mark.asyncio
async def test_query_resume_chunks_returns_empty_when_namespace_missing(monkeypatch):
    monkeypatch.setattr(vector_store_service, "_get_index", lambda: FakeIndex())

    matches = await query_resume_chunks(
        org_id="org_1",
        profile_id="profile_1",
        job_vector=[1.0, 0.0],
    )

    assert matches == []


@pytest.mark.asyncio
async def test_delete_resume_vectors_ignores_missing_namespace(monkeypatch):
    monkeypatch.setattr(vector_store_service, "_get_index", lambda: FakeIndex())

    await delete_resume_vectors_by_id("org_1", "resume_1", 1)


async def _async_value(value):
    return value


async def _async_append(items, value):
    items.append(value)
    return None


class FakeIndex:
    def fetch(self, **kwargs):
        raise FakeNamespaceNotFound()

    def query(self, **kwargs):
        raise FakeNamespaceNotFound()

    def delete(self, **kwargs):
        raise FakeNamespaceNotFound()


class FakeNamespaceNotFound(Exception):
    def __str__(self):
        return 'Reason: Not Found\nHTTP response body: {"code":5,"message":"Namespace not found","details":[]}'
