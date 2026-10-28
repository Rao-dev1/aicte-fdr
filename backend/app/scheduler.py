"""Daily maturity check, run on a schedule inside the backend process.

Runs at DAILY_CHECK_TIME (Indian time, default 08:00). If the server was off at that time, it runs once
shortly after the next start-up. Running it twice on the same day is harmless: status changes and
reminders are only created once.

Limitation: the schedule lives in the backend process, so it needs exactly one running backend instance.
When hosting moves to several instances, switch to a managed scheduler (Inngest or host cron).
"""

import json
import logging
import os
from datetime import date, datetime, time as dtime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from sqlalchemy import select

from .db import SessionLocal
from .lifecycle import lifecycle_sweep
from .models import JobRun, utcnow

log = logging.getLogger("fdr.scheduler")

JOB_NAME = "daily_maturity_check"
JOB_ID = "daily_maturity_check"
TZ = ZoneInfo("Asia/Kolkata")


def today_ist() -> date:
    return datetime.now(TZ).date()


def scheduled_time() -> dtime:
    raw = os.getenv("DAILY_CHECK_TIME", "08:00")
    hour, minute = (int(part) for part in raw.split(":"))
    return dtime(hour=hour, minute=minute, tzinfo=TZ)


def run_daily_check(trigger: str = "schedule") -> dict:
    """Runs the sweep and records the outcome in job_runs. Never raises; failures are recorded."""
    with SessionLocal() as db:
        run = JobRun(job=JOB_NAME, trigger=trigger, status="RUNNING", detail="", started_at=utcnow())
        db.add(run)
        db.commit()
        run_id = run.id
        try:
            result = lifecycle_sweep(db, today_ist())
            status, detail = "OK", json.dumps(result)
        except Exception as exc:  # recorded for the admin; the scheduler keeps running
            db.rollback()
            log.exception("Daily maturity check failed")
            status, detail, result = "FAILED", str(exc)[:500], {}

        run = db.get(JobRun, run_id)
        run.status = status
        run.detail = detail
        run.finished_at = utcnow()
        db.commit()
        return {"run_id": run_id, "status": status, **result, **({} if status == "OK" else {"error": detail})}


def _ran_successfully_today() -> bool:
    today_start = datetime.combine(today_ist(), dtime(0, 0), tzinfo=TZ)
    with SessionLocal() as db:
        return (
            db.scalar(
                select(JobRun.id).where(
                    JobRun.job == JOB_NAME,
                    JobRun.status == "OK",
                    JobRun.started_at >= today_start,
                )
            )
            is not None
        )


def start_scheduler(enabled: bool | None = None, catch_up: bool = True) -> BackgroundScheduler | None:
    if enabled is None:
        enabled = os.getenv("SCHEDULER_ENABLED", "1") == "1"
    if not enabled:
        return None

    sched = BackgroundScheduler(timezone=TZ)
    when = scheduled_time()
    sched.add_job(
        run_daily_check,
        CronTrigger(hour=when.hour, minute=when.minute, timezone=TZ),
        id=JOB_ID,
        kwargs={"trigger": "schedule"},
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    sched.start()

    now = datetime.now(TZ)
    if catch_up and now.timetz().replace(tzinfo=None) >= when.replace(tzinfo=None) and not _ran_successfully_today():
        sched.add_job(
            run_daily_check,
            DateTrigger(run_date=now),
            kwargs={"trigger": "catch-up"},
            id="daily_maturity_check_catch_up",
            replace_existing=True,
        )
        log.info("Server started after the scheduled time with no successful check today; running catch-up.")
    return sched
