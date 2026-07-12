from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "phitron_edtech",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Dhaka",
    enable_utc=True,
    beat_schedule={
        "streak-check-10pm": {
            "task": "app.tasks.background.run_streak_check",
            "schedule": crontab(hour=22, minute=0),
        },
        "pair-challenge-match-10am": {
            "task": "app.tasks.background.run_pair_challenge_matching",
            "schedule": crontab(hour=10, minute=0),
        },
        "pair-challenge-rematch-12pm": {
            "task": "app.tasks.background.run_pair_challenge_rematch",
            "schedule": crontab(hour=12, minute=0),
        },
    },
)

celery_app.autodiscover_tasks(["app.tasks"])
