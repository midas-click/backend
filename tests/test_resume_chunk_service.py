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
async def test_replace_resume_chunks_uses_vector_store(monkeypatch):
    calls = []
    vectors = [SimpleNamespace(id="resume:resume_1:0", values=[0.0, 0.0, 1.0], metadata={})]

    async def fake_upsert_resume_chunks(resume, sections):
        calls.append((resume, sections))
        return vectors

    monkeypatch.setattr(resume_chunk_service, "upsert_resume_chunks", fake_upsert_resume_chunks)
    resume = SimpleNamespace(id="resume_1")
    sections = [ResumeSection(title="Experience", content="Built APIs")]

    result = await replace_resume_chunks(resume, sections)

    assert result == vectors
    assert calls == [(resume, sections)]
