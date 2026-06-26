from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import APIRouter
from pydantic import BaseModel, Field

from domain.scheduler import SchedulerJobInfo
from services.system_info import run_command

scheduler_db = Path.cwd() / "scheduler_jobs.sqlite"
jobstore = {"default": SQLAlchemyJobStore(url=f"sqlite:///{scheduler_db}")}

scheduler = AsyncIOScheduler(jobstores=jobstore, job_defaults={"coalesce": False, "max_instances": 1})
router = APIRouter(prefix="/scheduler", tags=["scheduler"])


def get_scheduler():
    """Call scheduler.start() inside your app's lifespan, e.g.:

    from contextlib import asynccontextmanager
    from fastapi import FastAPI
    from scheduler import scheduler

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        scheduler.start()
        yield
        scheduler.shutdown()

    app = FastAPI(lifespan=lifespan)
    app.include_router(router)
    """
    return scheduler



def command_runner(command: str, args: List[str]) -> None:
    run_command([command, *args])


def serialize_job(job) -> SchedulerJobInfo:
    return SchedulerJobInfo(
        id=job.id,
        command=job.kwargs.get("command", ""),
        args=job.kwargs.get("args", []),
        next_run_time=job.next_run_time,
        trigger=str(job.trigger),
        recurring=job.kwargs.get("recurring"),
        run_at=job.next_run_time or datetime.now(timezone.utc),
    )
