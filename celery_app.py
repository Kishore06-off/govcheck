import os

from celery import Celery
from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str) -> str:
    v = os.getenv(name)
    return v if v is not None and v != "" else default


celery_app = Celery(
    "govcheck",
    broker=_env("CELERY_BROKER_URL", _env("REDIS_URL", "redis://localhost:6379/0")),
    backend=_env("CELERY_RESULT_BACKEND", _env("REDIS_URL", "redis://localhost:6379/0")),
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=int(_env("CELERY_WORKER_PREFETCH_MULTIPLIER", "1")),
    worker_max_tasks_per_child=int(_env("CELERY_MAX_TASKS_PER_CHILD", "30")),
)

