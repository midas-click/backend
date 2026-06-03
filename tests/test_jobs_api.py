from types import SimpleNamespace

import pytest
from bson import ObjectId
from fastapi import HTTPException

from app.api.v1 import jobs as jobs_api
from app.models.job import JobAnalyzeRequest
from app.services.job_page_validation_service import JobPageValidationResult


class ComparableField:
    def __eq__(self, other):
        return ("eq", other)


class FakeJobDocument:
    source_url = ComparableField()
    existing_source_url = None
    inserted = []

    def __init__(self, **kwargs):
        self.id = ObjectId()
        self.deleted = False
        for key, value in kwargs.items():
            setattr(self, key, value)

    @classmethod
    async def find_one(cls, expression):
        if cls.existing_source_url:
            return SimpleNamespace(id=ObjectId(), source_url=cls.existing_source_url)
        return None

    async def insert(self):
        self.__class__.inserted.append(self)
        return self

    async def save(self):
        return self


@pytest.fixture(autouse=True)
def fake_job_document(monkeypatch):
    FakeJobDocument.existing_source_url = None
    FakeJobDocument.inserted = []
    monkeypatch.setattr(jobs_api, "JobDocument", FakeJobDocument)


def _ctx():
    return {
        "user_id": "user_1",
        "org_id": "org_1",
        "org_role": "org:member",
        "profile_id": "profile_1",
    }


# Normalizes source URLs before duplicate checks so trailing slashes do not bypass uniqueness.
@pytest.mark.asyncio
async def test_ensure_source_url_available_trims_trailing_slash():
    source_url = await jobs_api._ensure_source_url_available("https://jobs.example/role/")

    assert source_url == "https://jobs.example/role"


# Rejects creating a job when another job already uses the same posting URL.
@pytest.mark.asyncio
async def test_ensure_source_url_available_rejects_duplicate_url():
    FakeJobDocument.existing_source_url = "https://jobs.example/role"

    with pytest.raises(HTTPException) as exc:
        await jobs_api._ensure_source_url_available("https://jobs.example/role")

    assert exc.value.status_code == 409


# Blocks LLM extraction and persistence when the submitted page fails job-page validation.
@pytest.mark.asyncio
async def test_analyze_and_create_job_rejects_non_job_page_before_llm(monkeypatch):
    llm_called = False

    async def fake_extract_job_fields(raw_text):
        nonlocal llm_called
        llm_called = True
        return {}

    monkeypatch.setattr(jobs_api, "extract_job_fields", fake_extract_job_fields)
    monkeypatch.setattr(
        jobs_api,
        "validate_job_page",
        lambda raw_text, source_url: JobPageValidationResult(
            is_job_page=False,
            confidence=0.1,
            reason="This page does not look like a job description",
            signals=["page text is too short"],
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await jobs_api.analyze_and_create_job(
            JobAnalyzeRequest(raw_text="shopping cart", source_url="https://shop.example/product"),
        )

    assert exc.value.status_code == 422
    assert exc.value.detail["message"] == (
        "This page does not look like a job description. "
        "Try opening a job posting or company careers page."
    )
    assert exc.value.detail["confidence"] == 0.1
    assert exc.value.detail["signals"] == ["page text is too short"]
    assert llm_called is False
    assert FakeJobDocument.inserted == []


# Creates an analyzed job from extracted fields and enqueues embedding after insert.
@pytest.mark.asyncio
async def test_analyze_and_create_job_inserts_extracted_job_and_enqueues(monkeypatch):
    enqueued = []
    monkeypatch.setattr(
        jobs_api,
        "validate_job_page",
        lambda raw_text, source_url: JobPageValidationResult(
            is_job_page=True,
            confidence=0.9,
            reason="Page looks like a job description",
            signals=["job section"],
        ),
    )
    monkeypatch.setattr(
        jobs_api,
        "extract_job_fields",
        lambda raw_text: _async_value({
            "title": "Backend Engineer",
            "company": "Midas",
            "location": "Remote",
            "remote": True,
            "salary_range": "$100k",
            "tags": ["python"],
        }),
    )
    monkeypatch.setattr(jobs_api, "enqueue_job_embedding", lambda job, source_text=None: _async_append(enqueued, (job, source_text)))

    job = await jobs_api.analyze_and_create_job(
        JobAnalyzeRequest(raw_text="Responsibilities and qualifications", source_url="https://jobs.example/role/"),
    )

    assert job.title == "Backend Engineer"
    assert job.company == "Midas"
    assert job.source_url == "https://jobs.example/role"
    assert not hasattr(job, "description")
    assert enqueued == [(job, "Responsibilities and qualifications")]


async def _async_value(value):
    return value


async def _async_append(items, value):
    items.append(value)
    return True
