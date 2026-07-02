import ssl

from celery import Celery

from app.config.settings import get_settings

settings = get_settings()
redis_url = settings.redis.url

celery_app = Celery("contagion")

config: dict = {
    "broker_url": redis_url,
    "result_backend": redis_url,
    "task_serializer": "json",
    "accept_content": ["json"],
    "result_serializer": "json",
    "timezone": "UTC",
    "enable_utc": True,
    "task_track_started": True,
    "worker_prefetch_multiplier": 1,
}

if redis_url.startswith("rediss://"):
    ssl_options = {"ssl_cert_reqs": ssl.CERT_REQUIRED}
    config["broker_use_ssl"] = ssl_options
    config["redis_backend_use_ssl"] = ssl_options

celery_app.conf.update(**config)

celery_app.autodiscover_tasks(["app.tasks"])
