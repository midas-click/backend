from io import BytesIO

import pytest
from bson import ObjectId
from fastapi import UploadFile

from app.api.v1 import resumes as resumes_api
from app.models.resume import ResumeSection


def _upload_file():
    return UploadFile(file=BytesIO(b"resume text"), filename="resume.txt")


class FakeResumeDocument:
    def __init__(self, **kwargs):
        self.id = None
        for key, value in kwargs.items():
            setattr(self, key, value)

    async def insert(self):
        self.id = ObjectId()
        return self

    async def delete(self):
        return None

    async def save(self):
        return self


@pytest.mark.asyncio
async def test_upload_resume_queues_embeddings(monkeypatch):
    queued = []

    async def fake_parse_resume_bytes(filename, content):
        return "resume text", [ResumeSection(title="Experience", content="Built APIs")]

    async def fake_upload_to_s3(key, content, content_type):
        return "https://example.com/resume.txt"

    async def fake_enqueue_resume_embedding(resume):
        queued.append(resume)
        resume.embedding_status = "pending"
        return True

    monkeypatch.setattr(resumes_api, "parse_resume_bytes", fake_parse_resume_bytes)
    monkeypatch.setattr(resumes_api, "upload_to_s3", fake_upload_to_s3)
    monkeypatch.setattr(resumes_api, "enqueue_resume_embedding", fake_enqueue_resume_embedding)
    monkeypatch.setattr(resumes_api, "ResumeDocument", FakeResumeDocument)

    resume = await resumes_api.upload_resume(
        _upload_file(),
        ctx={"user_id": "user_1", "org_id": "org_1", "profile_id": "profile_1"},
    )

    assert resume.original_filename == "resume.txt"
    assert resume.raw_text == "resume text"
    assert queued == [resume]
    assert resume.embedding_status == "pending"


@pytest.mark.asyncio
async def test_upload_resume_returns_resume_when_embedding_queue_fails(monkeypatch):

    async def fake_parse_resume_bytes(filename, content):
        return "resume text", [ResumeSection(title="Experience", content="Built APIs")]

    async def fake_upload_to_s3(key, content, content_type):
        return "https://example.com/resume.txt"

    async def fake_enqueue_resume_embedding(resume):
        resume.embedding_status = "failed"
        resume.embedding_error = "Failed to queue embedding job"
        return False

    monkeypatch.setattr(resumes_api, "parse_resume_bytes", fake_parse_resume_bytes)
    monkeypatch.setattr(resumes_api, "upload_to_s3", fake_upload_to_s3)
    monkeypatch.setattr(resumes_api, "enqueue_resume_embedding", fake_enqueue_resume_embedding)
    monkeypatch.setattr(resumes_api, "ResumeDocument", FakeResumeDocument)

    resume = await resumes_api.upload_resume(
        _upload_file(),
        ctx={"user_id": "user_1", "org_id": "org_1", "profile_id": "profile_1"},
    )

    assert resume.original_filename == "resume.txt"
    assert resume.embedding_status == "failed"
    assert resume.embedding_error == "Failed to queue embedding job"


@pytest.mark.asyncio
async def test_upload_resume_skips_embeddings_when_disabled(monkeypatch):
    queued = []

    async def fake_parse_resume_bytes(filename, content):
        return "resume text", [ResumeSection(title="Experience", content="Built APIs")]

    async def fake_upload_to_s3(key, content, content_type):
        return "https://example.com/resume.txt"

    async def fake_enqueue_resume_embedding(resume):
        queued.append(resume)
        resume.embedding_status = "disabled"
        return False

    monkeypatch.setattr(resumes_api, "parse_resume_bytes", fake_parse_resume_bytes)
    monkeypatch.setattr(resumes_api, "upload_to_s3", fake_upload_to_s3)
    monkeypatch.setattr(resumes_api, "enqueue_resume_embedding", fake_enqueue_resume_embedding)
    monkeypatch.setattr(resumes_api, "ResumeDocument", FakeResumeDocument)

    resume = await resumes_api.upload_resume(
        _upload_file(),
        ctx={"user_id": "user_1", "org_id": "org_1", "profile_id": "profile_1"},
    )

    assert resume.original_filename == "resume.txt"
    assert queued == [resume]
    assert resume.embedding_status == "disabled"
