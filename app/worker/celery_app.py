"""Celery application for MidasClick background workers."""

from celery import Celery

from app.config import settings

celery_app = Celery(
    "midas_click",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.worker.embedding_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)
