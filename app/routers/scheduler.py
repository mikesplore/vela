from typing import Any

from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_current_user
from app.domain.scheduler import SchedulerActionResponse, SchedulerCreateRequest, SchedulerListResponse
from app.services.scheduler import command_runner, scheduler, serialize_job

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
        job.func(**job.kwargs)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    return SchedulerActionResponse(success=True, message=f"Triggered task {task_id} immediately")
