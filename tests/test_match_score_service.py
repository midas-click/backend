from types import SimpleNamespace

import pytest

from app.services import match_score_service
from app.services.match_score_service import calculate_match_score, score_resumes_for_job


class FakeFindResult:
    def __init__(self, items):
        self.items = items

    async def to_list(self):
        return self.items


class FakeJobChunkDocument:
    filters = []

    @classmethod
    def find(cls, filters):
        cls.filters.append(filters)
        return FakeFindResult([
            SimpleNamespace(embedding=[1.0, 0.0]),
            SimpleNamespace(embedding=[0.0, 1.0]),
        ])


class FakeResumeChunkDocument:
    @classmethod
    def find(cls, filters):
        return FakeFindResult([
            SimpleNamespace(embedding=[1.0, 0.0]),
            SimpleNamespace(embedding=[0.0, 1.0]),
        ])


@pytest.mark.asyncio
async def test_calculate_match_score_uses_best_resume_chunks(monkeypatch):
    FakeJobChunkDocument.filters = []
    monkeypatch.setattr(match_score_service, "JobChunkDocument", FakeJobChunkDocument)
    monkeypatch.setattr(match_score_service, "ResumeChunkDocument", FakeResumeChunkDocument)

    score = await calculate_match_score("job_1", "resume_1", "org_1")

    assert score == 100.0
    assert FakeJobChunkDocument.filters == [{"job_id": "job_1"}]


@pytest.mark.asyncio
async def test_score_resumes_for_job_returns_resume_metadata(monkeypatch):
    monkeypatch.setattr(match_score_service, "JobChunkDocument", FakeJobChunkDocument)
    monkeypatch.setattr(match_score_service, "ResumeChunkDocument", FakeResumeChunkDocument)
    resumes = [
        SimpleNamespace(id="resume_1", original_filename="resume.pdf"),
    ]

    scores = await score_resumes_for_job("job_1", resumes, "org_1")

    assert scores[0].resume_id == "resume_1"
    assert scores[0].resume_filename == "resume.pdf"
    assert scores[0].match_score == 100.0
