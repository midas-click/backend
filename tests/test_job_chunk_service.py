from types import SimpleNamespace

import pytest

from app.services import job_chunk_service
from app.services.job_chunk_service import chunk_job, replace_job_chunks


def test_chunk_job_includes_core_job_fields_and_source_text():
    job = SimpleNamespace(
        title="Backend Engineer",
        company="Midas",
        location="Remote",
        salary_range="$100k-$120k",
        tags=["python", "mongodb"],
    )

    chunks = chunk_job(job, source_text="Build APIs", max_chars=1000)

    assert len(chunks) == 1
    assert "Title: Backend Engineer" in chunks[0].content
    assert "Tags: python, mongodb" in chunks[0].content
    assert "Job text:\nBuild APIs" in chunks[0].content


@pytest.mark.asyncio
async def test_replace_job_chunks_uses_vector_store(monkeypatch):
    calls = []
    vectors = [SimpleNamespace(id="job:job_1:0", values=[1.0, 0.0, 0.0], metadata={})]

    async def fake_upsert_job_chunks(job, source_text=None):
        calls.append((job, source_text))
        return vectors

    monkeypatch.setattr(job_chunk_service, "upsert_job_chunks", fake_upsert_job_chunks)
    job = SimpleNamespace(id="job_1")

    result = await replace_job_chunks(job, "Build APIs")

    assert result == vectors
    assert calls == [(job, "Build APIs")]
