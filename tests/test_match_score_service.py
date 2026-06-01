from types import SimpleNamespace

import pytest

from app.services import match_score_service
from app.services.match_score_service import calculate_match_score, score_resumes_for_job
from app.services.vector_store_service import StoredVector, VectorMatch


class FakeJobDocument:
    @classmethod
    async def get(cls, job_id):
        return SimpleNamespace(
            id=job_id,
            org_id="org_1",
            embedding_status="completed",
            vector_chunk_count=2,
        )


class FakeResumeDocument:
    @classmethod
    async def get(cls, resume_id):
        return SimpleNamespace(
            id=resume_id,
            org_id="org_1",
            original_filename="resume.pdf",
            embedding_status="completed",
            vector_chunk_count=1,
        )


@pytest.mark.asyncio
async def test_calculate_match_score_uses_pinecone_matches(monkeypatch):
    queries = []
    monkeypatch.setattr(match_score_service, "JobDocument", FakeJobDocument)
    monkeypatch.setattr(match_score_service, "ResumeDocument", FakeResumeDocument)
    monkeypatch.setattr(
        match_score_service,
        "fetch_job_vectors",
        lambda job: _async_value([
            StoredVector(id="job:job_1:0", values=[1.0, 0.0], metadata={}),
            StoredVector(id="job:job_1:1", values=[0.0, 1.0], metadata={}),
        ]),
    )

    async def fake_query_resume_chunks(**kwargs):
        queries.append(kwargs)
        return [VectorMatch(id="resume:resume_1:0", score=1.0, metadata={"resume_id": "resume_1"})]

    monkeypatch.setattr(match_score_service, "query_resume_chunks", fake_query_resume_chunks)

    score = await calculate_match_score("job_1", "resume_1", "org_1")

    assert score == 100.0
    assert [query["resume_id"] for query in queries] == ["resume_1", "resume_1"]


@pytest.mark.asyncio
async def test_score_resumes_for_job_returns_resume_metadata(monkeypatch):
    monkeypatch.setattr(match_score_service, "JobDocument", FakeJobDocument)
    monkeypatch.setattr(
        match_score_service,
        "fetch_job_vectors",
        lambda job: _async_value([StoredVector(id="job:job_1:0", values=[1.0, 0.0], metadata={})]),
    )
    monkeypatch.setattr(
        match_score_service,
        "query_resume_chunks",
        lambda **kwargs: _async_value([VectorMatch(id="resume:resume_1:0", score=1.0, metadata={})]),
    )
    resumes = [
        SimpleNamespace(
            id="resume_1",
            org_id="org_1",
            original_filename="resume.pdf",
            embedding_status="completed",
            vector_chunk_count=1,
        ),
    ]

    scores = await score_resumes_for_job("job_1", resumes, "org_1")

    assert scores[0].resume_id == "resume_1"
    assert scores[0].resume_filename == "resume.pdf"
    assert scores[0].match_score == 100.0


@pytest.mark.asyncio
async def test_calculate_match_score_returns_none_without_job_vectors(monkeypatch):
    monkeypatch.setattr(match_score_service, "JobDocument", FakeJobDocument)
    monkeypatch.setattr(match_score_service, "ResumeDocument", FakeResumeDocument)
    monkeypatch.setattr(match_score_service, "fetch_job_vectors", lambda job: _async_value([]))

    assert await calculate_match_score("job_1", "resume_1", "org_1") is None


@pytest.mark.asyncio
async def test_score_resumes_for_job_explains_job_embedding_not_ready(monkeypatch):
    class PendingJobDocument:
        @classmethod
        async def get(cls, job_id):
            return SimpleNamespace(
                id=job_id,
                org_id="org_1",
                embedding_status="processing",
                vector_chunk_count=0,
            )

    monkeypatch.setattr(match_score_service, "JobDocument", PendingJobDocument)
    resumes = [
        SimpleNamespace(
            id="resume_1",
            org_id="org_1",
            original_filename="resume.pdf",
            embedding_status="completed",
            vector_chunk_count=1,
        ),
    ]

    scores = await score_resumes_for_job("job_1", resumes, "org_1")

    assert scores[0].match_score is None
    assert scores[0].match_explanation == (
        "Job embedding is still processing; match score will be available after embedding completes."
    )


@pytest.mark.asyncio
async def test_score_resumes_for_job_explains_resume_embedding_not_ready(monkeypatch):
    monkeypatch.setattr(match_score_service, "JobDocument", FakeJobDocument)
    resumes = [
        SimpleNamespace(
            id="resume_1",
            org_id="org_1",
            original_filename="resume.pdf",
            embedding_status="pending",
            vector_chunk_count=0,
        ),
    ]

    scores = await score_resumes_for_job("job_1", resumes, "org_1")

    assert scores[0].match_score is None
    assert scores[0].match_explanation == (
        "Resume embedding is still pending; match score will be available after embedding completes."
    )


async def _async_value(value):
    return value
