from celery import Celery
from backend.app.core.config import settings

celery_app = Celery(
    "tracelens",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=1800,
    task_time_limit=2400,
    beat_schedule={
        "check-scheduled-rechecks": {
            "task": "worker.tasks.process_scheduled_rechecks",
            "schedule": 3600.0,  # Every hour
        },
    },
)
