from types import SimpleNamespace

from fastapi import BackgroundTasks

from app.services import vector_cleanup_queue_service


def test_job_vector_cleanup_is_scheduled_after_response(monkeypatch):
    monkeypatch.setattr(vector_cleanup_queue_service.settings, "EMBEDDINGS_ASYNC_ENABLED", False)
    background_tasks = BackgroundTasks()
    job = SimpleNamespace(id="job_1", org_id="org_1", vector_chunk_count=2)

    vector_cleanup_queue_service.enqueue_job_vector_cleanup(job, background_tasks)

    assert len(background_tasks.tasks) == 1


def test_job_vector_cleanup_skips_jobs_without_vectors():
    background_tasks = BackgroundTasks()
    job = SimpleNamespace(id="job_1", org_id="org_1", vector_chunk_count=0)

    vector_cleanup_queue_service.enqueue_job_vector_cleanup(job, background_tasks)

    assert background_tasks.tasks == []
