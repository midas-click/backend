"""Celery application for MidasClick background workers."""

from celery import Celery

from app.config import settings

celery_app = Celery(
    "midas_click",
    broker=settings.celery_broker_url,
    include=["app.worker.embedding_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_transport_options=settings.celery_broker_transport_options,
    task_default_queue=settings.CELERY_TASK_DEFAULT_QUEUE,
    task_ignore_result=True,
    result_backend=None,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)
