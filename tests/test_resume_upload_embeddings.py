from io import BytesIO

import pytest
from bson import ObjectId
from fastapi import HTTPException, UploadFile

from app.api.v1 import resumes as resumes_api
from app.models.resume import ResumeSection
from app.services.embedding_service import EmbeddingServiceError


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


@pytest.mark.asyncio
async def test_upload_resume_creates_embeddings(monkeypatch):
    embedded = []

    async def fake_parse_resume_bytes(filename, content):
        return "resume text", [ResumeSection(title="Experience", content="Built APIs")]

    async def fake_upload_to_s3(key, content, content_type):
        return "https://example.com/resume.txt"

    async def fake_replace_resume_chunks(resume, sections):
        embedded.append((resume, sections))

    monkeypatch.setattr(resumes_api, "parse_resume_bytes", fake_parse_resume_bytes)
    monkeypatch.setattr(resumes_api, "upload_to_s3", fake_upload_to_s3)
    monkeypatch.setattr(resumes_api, "replace_resume_chunks", fake_replace_resume_chunks)
    monkeypatch.setattr(resumes_api, "ResumeDocument", FakeResumeDocument)
    monkeypatch.setattr(resumes_api.settings, "EMBEDDINGS_ENABLED", True)

    resume = await resumes_api.upload_resume(
        _upload_file(),
        ctx={"user_id": "user_1", "org_id": "org_1", "profile_id": "profile_1"},
    )

    assert resume.original_filename == "resume.txt"
    assert resume.raw_text == "resume text"
    assert embedded[0][0] == resume
    assert embedded[0][1][0].title == "Experience"


@pytest.mark.asyncio
async def test_upload_resume_fails_when_embedding_fails(monkeypatch):
    deleted = []

    async def fake_parse_resume_bytes(filename, content):
        return "resume text", [ResumeSection(title="Experience", content="Built APIs")]

    async def fake_upload_to_s3(key, content, content_type):
        return "https://example.com/resume.txt"

    async def fake_delete(self):
        deleted.append(self.original_filename)

    async def fake_replace_resume_chunks(resume, sections):
        raise EmbeddingServiceError("Failed to generate resume embeddings")

    monkeypatch.setattr(resumes_api, "parse_resume_bytes", fake_parse_resume_bytes)
    monkeypatch.setattr(resumes_api, "upload_to_s3", fake_upload_to_s3)
    monkeypatch.setattr(resumes_api, "replace_resume_chunks", fake_replace_resume_chunks)
    monkeypatch.setattr(resumes_api, "ResumeDocument", FakeResumeDocument)
    monkeypatch.setattr(FakeResumeDocument, "delete", fake_delete)
    monkeypatch.setattr(resumes_api.settings, "EMBEDDINGS_ENABLED", True)

    with pytest.raises(HTTPException) as exc:
        await resumes_api.upload_resume(
            _upload_file(),
            ctx={"user_id": "user_1", "org_id": "org_1", "profile_id": "profile_1"},
        )

    assert exc.value.status_code == 502
    assert "Failed to generate resume embeddings" in exc.value.detail
    assert deleted == ["resume.txt"]


@pytest.mark.asyncio
async def test_upload_resume_skips_embeddings_when_disabled(monkeypatch):
    embedded = []

    async def fake_parse_resume_bytes(filename, content):
        return "resume text", [ResumeSection(title="Experience", content="Built APIs")]

    async def fake_upload_to_s3(key, content, content_type):
        return "https://example.com/resume.txt"

    async def fake_replace_resume_chunks(resume, sections):
        embedded.append((resume, sections))

    monkeypatch.setattr(resumes_api, "parse_resume_bytes", fake_parse_resume_bytes)
    monkeypatch.setattr(resumes_api, "upload_to_s3", fake_upload_to_s3)
    monkeypatch.setattr(resumes_api, "replace_resume_chunks", fake_replace_resume_chunks)
    monkeypatch.setattr(resumes_api, "ResumeDocument", FakeResumeDocument)
    monkeypatch.setattr(resumes_api.settings, "EMBEDDINGS_ENABLED", False)

    resume = await resumes_api.upload_resume(
        _upload_file(),
        ctx={"user_id": "user_1", "org_id": "org_1", "profile_id": "profile_1"},
    )

    assert resume.original_filename == "resume.txt"
    assert embedded == []
