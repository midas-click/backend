from types import SimpleNamespace

import pytest
from bson import ObjectId
from fastapi import HTTPException

from app.api.v1 import applications as applications_api
from app.models.application import (
    ApplicationBatchCreate,
    ApplicationCreate,
    CommunicationCreate,
    StageChange,
)


class FakeApplicationDocument:
    inserted = []
    document_by_id = {}

    def __init__(self, **kwargs):
        self.id = ObjectId()
        self.communication_log = []
        self.timeline = []
        for key, value in kwargs.items():
            setattr(self, key, value)

    async def insert(self):
        self.__class__.inserted.append(self)
        return self

    @classmethod
    async def get(cls, app_id):
        return cls.document_by_id.get(str(app_id))

    async def save(self):
        return self

    async def delete(self):
        self.deleted = True


class FakeJobDocument:
    jobs_by_id = {}
    find_filter = None

    @classmethod
    async def get(cls, job_id):
        return cls.jobs_by_id.get(str(job_id))

    @classmethod
    def find(cls, query):
        cls.find_filter = query
        ids = {str(item) for item in query["_id"]["$in"]}
        jobs = [job for job_id, job in cls.jobs_by_id.items() if job_id in ids]
        return SimpleNamespace(to_list=lambda: _async_value(jobs))


class FakeResumeDocument:
    resumes_by_id = {}
    default_resume = None
    find_filter = None

    @classmethod
    async def get(cls, resume_id):
        return cls.resumes_by_id.get(str(resume_id))

    @classmethod
    def find(cls, query):
        cls.find_filter = query
        return FakeResumeQuery(cls.default_resume)


class FakeResumeQuery:
    def __init__(self, resume):
        self.resume = resume

    def sort(self, *args):
        return self

    async def first_or_none(self):
        return self.resume


async def _async_value(value):
    return value


@pytest.fixture(autouse=True)
def fake_documents(monkeypatch):
    FakeApplicationDocument.inserted = []
    FakeApplicationDocument.document_by_id = {}
    FakeJobDocument.jobs_by_id = {}
    FakeJobDocument.find_filter = None
    FakeResumeDocument.resumes_by_id = {}
    FakeResumeDocument.default_resume = None
    FakeResumeDocument.find_filter = None
    monkeypatch.setattr(applications_api, "ApplicationDocument", FakeApplicationDocument)
    monkeypatch.setattr(applications_api, "JobDocument", FakeJobDocument)
    monkeypatch.setattr(applications_api, "ResumeDocument", FakeResumeDocument)


def _ctx(profile_id="profile_1"):
    return {"user_id": "user_1", "org_id": "org_1", "profile_id": profile_id}


# Creates an application with source URL and resume filename denormalized from linked records.
@pytest.mark.asyncio
async def test_create_application_denormalizes_job_and_resume_fields(monkeypatch):
    job_id = str(ObjectId())
    resume_id = str(ObjectId())
    FakeJobDocument.jobs_by_id[job_id] = SimpleNamespace(id=job_id, source_url="https://jobs.example/1")
    FakeResumeDocument.resumes_by_id[resume_id] = SimpleNamespace(
        id=resume_id,
        org_id="org_1",
        original_filename="resume.pdf",
    )
    monkeypatch.setattr(applications_api, "score_resume_for_job", _async_value_none)

    app = await applications_api.create_application(
        ApplicationCreate(job_id=job_id, resume_id=resume_id, job_title="Engineer", company="Midas"),
        _ctx(),
    )

    assert app.source_url == "https://jobs.example/1"
    assert app.resume_filename == "resume.pdf"
    assert app.timeline[0].event == "Applied"


# Preserves a frontend-provided match score instead of recalculating it in the backend.
@pytest.mark.asyncio
async def test_create_application_does_not_recalculate_when_match_score_is_supplied(monkeypatch):
    calls = []

    async def fake_score_resume_for_job(*args):
        calls.append(args)
        return None

    monkeypatch.setattr(applications_api, "score_resume_for_job", fake_score_resume_for_job)

    app = await applications_api.create_application(
        ApplicationCreate(
            job_id=str(ObjectId()),
            resume_id=str(ObjectId()),
            job_title="Engineer",
            company="Midas",
            match_score=88.5,
            match_explanation="Provided by frontend",
        ),
        _ctx(),
    )

    assert calls == []
    assert app.match_score == 88.5
    assert app.match_explanation == "Provided by frontend"


# Rejects batch application creation when any selected job id is malformed.
@pytest.mark.asyncio
async def test_create_applications_batch_rejects_invalid_job_id():
    with pytest.raises(HTTPException) as exc:
        await applications_api.create_applications_batch(
            ApplicationBatchCreate(job_ids=["not-an-object-id"]),
            _ctx(),
        )

    assert exc.value.status_code == 400
    assert "invalid" in exc.value.detail


# Deduplicates selected jobs and creates applications from the default resume in order.
@pytest.mark.asyncio
async def test_create_applications_batch_deduplicates_jobs_and_uses_default_resume(monkeypatch):
    job_id = str(ObjectId())
    resume_id = str(ObjectId())
    FakeResumeDocument.default_resume = SimpleNamespace(
        id=resume_id,
        original_filename="default.pdf",
    )
    FakeJobDocument.jobs_by_id[job_id] = SimpleNamespace(
        id=ObjectId(job_id),
        title="Engineer",
        company="Midas",
        location="Remote",
        source_url="https://jobs.example/1",
        salary_range="$100k",
        tags=["python"],
    )

    async def fake_calculate_match_score(*args):
        return 72.0

    monkeypatch.setattr(applications_api, "calculate_match_score", fake_calculate_match_score)

    apps = await applications_api.create_applications_batch(
        ApplicationBatchCreate(job_ids=[job_id, job_id]),
        _ctx(),
    )

    assert len(apps) == 1
    assert apps[0].resume_id == resume_id
    assert apps[0].resume_filename == "default.pdf"
    assert apps[0].match_score == 72.0


# Appends both communication history and timeline entries for a new communication.
@pytest.mark.asyncio
async def test_add_communication_appends_log_and_timeline(monkeypatch):
    app = FakeApplicationDocument(
        org_id="org_1",
        profile_id="profile_1",
        job_title="Engineer",
        company="Midas",
    )
    FakeApplicationDocument.document_by_id[str(app.id)] = app

    updated = await applications_api.add_communication(
        str(app.id),
        CommunicationCreate(channel="email", summary="Sent follow-up"),
        _ctx(),
    )

    assert updated.communication_log[0].summary == "Sent follow-up"
    assert updated.timeline[-1].event == "Communication: email"


# Moves an application stage and records the transition in the timeline.
@pytest.mark.asyncio
async def test_move_stage_updates_stage_and_records_timeline(monkeypatch):
    app = FakeApplicationDocument(
        org_id="org_1",
        profile_id="profile_1",
        stage="applied",
        job_title="Engineer",
        company="Midas",
    )
    FakeApplicationDocument.document_by_id[str(app.id)] = app

    updated = await applications_api.move_stage(
        str(app.id),
        StageChange(stage="technical", detail="Interview scheduled"),
        _ctx(),
    )

    assert updated.stage == "technical"
    assert updated.timeline[-1].event == "Moved: applied \u2192 technical"
    assert updated.timeline[-1].detail == "Interview scheduled"


async def _async_value_none(*args):
    return None
