from pathlib import Path
from typing import Any

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_current_user
from domain.scheduler import SchedulerActionResponse, SchedulerCreateRequest, SchedulerListResponse
from services.scheduler import command_runner, serialize_job

scheduler_db = Path.cwd() / "scheduler_jobs.sqlite"
jobstore = {"default": SQLAlchemyJobStore(url=f"sqlite:///{scheduler_db}")}

scheduler = AsyncIOScheduler(jobstores=jobstore, job_defaults={"coalesce": False, "max_instances": 1})
router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.post("/create", response_model=SchedulerActionResponse, dependencies=[Depends(get_current_user)])
async def create_job(request: SchedulerCreateRequest) -> Any:
    """Schedule a command to run at a specific time or on a cron schedule."""
    try:
        if request.recurring:
            trigger = CronTrigger.from_crontab(request.recurring)
            job = scheduler.add_job(
                command_runner,
                trigger=trigger,
                kwargs={"command": request.command, "args": request.args},
                replace_existing=False,
            )
        else:
            job = scheduler.add_job(
                command_runner,
                trigger="date",
                run_date=request.run_at,
                kwargs={"command": request.command, "args": request.args},
                replace_existing=False,
            )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return SchedulerActionResponse(success=True, message=f"Scheduled job {job.id}")


@router.get("/list", response_model=SchedulerListResponse, dependencies=[Depends(get_current_user)])
async def list_jobs() -> Any:
    """List all scheduled tasks."""
    jobs = [serialize_job(job) for job in scheduler.get_jobs()]
    return SchedulerListResponse(jobs=jobs)


@router.delete("/cancel/{task_id}", response_model=SchedulerActionResponse, dependencies=[Depends(get_current_user)])
async def cancel_job(task_id: str) -> Any:
    """Cancel a scheduled task."""
    job = scheduler.get_job(task_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    scheduler.remove_job(task_id)
    return SchedulerActionResponse(success=True, message=f"Cancelled task {task_id}")


@router.post("/run-now/{task_id}", response_model=SchedulerActionResponse, dependencies=[Depends(get_current_user)])
async def run_job_now(task_id: str) -> Any:
    """Trigger a scheduled task to run immediately."""
    job = scheduler.get_job(task_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    try:
        # Directly invoke the job's function instead of spawning a new scheduled job.
        # This avoids orphaned one-off jobs piling up in the job store and works
        # regardless of whether the scheduler is running.
        job.func(**job.kwargs)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    return SchedulerActionResponse(success=True, message=f"Triggered task {task_id} immediately")
