import builtins
import sys
from datetime import datetime
from types import ModuleType, SimpleNamespace

import pytest

from app.services import embedding_queue_service


class FakeEmbeddingOwner:
    def __init__(self):
        self.id = "owner_1"
        self.embedding_status = "disabled"
        self.embedding_error = None
        self.embedded_at = None
        self.vector_store = None
        self.vector_chunk_count = 0
        self.saved_snapshots = []

    async def save(self):
        self.saved_snapshots.append(
            (self.embedding_status, self.embedding_error, self.embedded_at)
        )
        return self


# Marks embeddings as disabled without trying to import Celery when embeddings are off.
@pytest.mark.asyncio
async def test_enqueue_job_embedding_marks_disabled_when_embeddings_off(monkeypatch):
    owner = FakeEmbeddingOwner()
    monkeypatch.setattr(embedding_queue_service.settings, "EMBEDDINGS_ENABLED", False)

    queued = await embedding_queue_service.enqueue_job_embedding(owner)

    assert queued is False
    assert owner.embedding_status == "disabled"
    assert owner.saved_snapshots[-1][0] == "disabled"


# Enqueues a Celery task and leaves the owner pending when async embeddings are enabled.
@pytest.mark.asyncio
async def test_enqueue_job_embedding_imports_task_and_delays(monkeypatch):
    owner = FakeEmbeddingOwner()
    delayed = []
    module = ModuleType("app.worker.embedding_tasks")
    module.embed_job_task = SimpleNamespace(delay=lambda owner_id, source_text=None: delayed.append((owner_id, source_text)))
    monkeypatch.setitem(sys.modules, "app.worker.embedding_tasks", module)
    monkeypatch.setattr(embedding_queue_service.settings, "EMBEDDINGS_ENABLED", True)
    monkeypatch.setattr(embedding_queue_service.settings, "EMBEDDINGS_ASYNC_ENABLED", True)

    queued = await embedding_queue_service.enqueue_job_embedding(owner, "Build APIs")

    assert queued is True
    assert delayed == [("owner_1", "Build APIs")]
    assert owner.embedding_status == "pending"
    assert owner.embedding_error is None


# Records a failed embedding status when the Celery task cannot be queued.
@pytest.mark.asyncio
async def test_enqueue_resume_embedding_marks_failed_when_task_import_fails(monkeypatch):
    owner = FakeEmbeddingOwner()
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "app.worker.embedding_tasks":
            raise ModuleNotFoundError("No module named 'celery'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(embedding_queue_service.settings, "EMBEDDINGS_ENABLED", True)
    monkeypatch.setattr(embedding_queue_service.settings, "EMBEDDINGS_ASYNC_ENABLED", True)

    queued = await embedding_queue_service.enqueue_resume_embedding(owner)

    assert queued is False
    assert owner.embedding_status == "failed"
    assert "Failed to queue embedding job" in owner.embedding_error


# Sets embedded_at only for completed embeddings and clears it for retried states.
@pytest.mark.asyncio
async def test_mark_embedding_status_sets_timestamp_only_for_completed():
    owner = FakeEmbeddingOwner()

    await embedding_queue_service.mark_embedding_status(owner, "completed")
    completed_at = owner.embedded_at
    await embedding_queue_service.mark_embedding_status(owner, "processing")

    assert isinstance(completed_at, datetime)
    assert owner.embedding_status == "processing"
    assert owner.embedded_at is None
