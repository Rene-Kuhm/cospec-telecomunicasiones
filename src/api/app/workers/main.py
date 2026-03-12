from arq import cron
from arq.connections import RedisSettings

from app.config import settings
from app.workers.exports import (
    annual_export,
    check_sla_breaches,
    daily_export,
    monthly_export,
    run_export,
)
from app.workers.geocoding import geocode_ticket
from app.workers.notifications import send_notification


class WorkerSettings:
    functions = [send_notification, geocode_ticket, run_export]
    cron_jobs = [
        cron(daily_export, hour=0, minute=5),
        cron(monthly_export, day=1, hour=0, minute=10),
        cron(annual_export, month=1, day=1, hour=0, minute=15),
        cron(check_sla_breaches, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
    ]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_jobs = settings.ARQ_MAX_JOBS
    job_timeout = settings.ARQ_JOB_TIMEOUT
    queue_name = settings.ARQ_QUEUE_NAME
