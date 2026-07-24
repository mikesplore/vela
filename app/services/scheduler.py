from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import APIRouter

from app.domain.scheduler import SchedulerJobInfo
from app.services.system_info import run_command

# Stable path — do not depend on process cwd (systemd uses /home/mike, dev uses project dir).
SCHEDULER_DB = Path.home() / ".config" / "vela" / "scheduler_jobs.sqlite"
SCHEDULER_DB.parent.mkdir(parents=True, exist_ok=True)

jobstore = {"default": SQLAlchemyJobStore(url=f"sqlite:///{SCHEDULER_DB}")}

scheduler = AsyncIOScheduler(jobstores=jobstore, job_defaults={"coalesce": False, "max_instances": 1})
router = APIRouter(prefix="/scheduler", tags=["scheduler"])


def get_scheduler() -> AsyncIOScheduler:
    return scheduler


def job_next_run_time(job: Any) -> datetime | None:
    """Return the next run time across APScheduler versions / partially loaded jobs."""
    for attr in ("next_run_time", "next_fire_time", "scheduled_fire_time"):
        value = getattr(job, attr, None)
        if value is not None:
            return value
    return None


def format_job_next_run(job: Any) -> str | None:
    next_run = job_next_run_time(job)
    return next_run.isoformat() if next_run else None


def command_runner(command: str, args: List[str]) -> None:
    run_command([command, *args])


def serialize_job(job) -> SchedulerJobInfo:
    next_run = job_next_run_time(job)
    return SchedulerJobInfo(
        id=job.id,
        command=job.kwargs.get("command", ""),
        args=job.kwargs.get("args", []),
        next_run_time=next_run,
        trigger=str(job.trigger),
        recurring=job.kwargs.get("recurring"),
        run_at=next_run or datetime.now(timezone.utc),
    )
