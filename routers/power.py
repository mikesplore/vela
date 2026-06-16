import subprocess
from datetime import datetime
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dependencies import get_current_user

router = APIRouter(prefix="/power", tags=["power"])


class ValueResponse(BaseModel):
    success: bool
    message: str


class ScheduleShutdownRequest(BaseModel):
    at: datetime


class PowerProfileRequest(BaseModel):
    profile: str = Field(..., pattern="^(performance|balanced|power-saver)$")


class PowerProfileResponse(BaseModel):
    success: bool
    message: str
    profile: str


def _run_command(cmd: List[str], timeout: int = 10) -> tuple[str, str, int]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        return "", str(exc), 1


def _power_action(cmd: List[str], success_message: str) -> ValueResponse:
    stdout, stderr, code = _run_command(cmd)
    if code != 0:
        raise HTTPException(status_code=500, detail=stderr or stdout or "power action failed")
    return ValueResponse(success=True, message=success_message)


def _power_profile_action(cmd: List[str], profile: str) -> PowerProfileResponse:
    stdout, stderr, code = _run_command(cmd)
    if code != 0:
        raise HTTPException(status_code=500, detail=stderr or stdout or "power profile action failed")
    return PowerProfileResponse(success=True, message=f"profile set to {profile}", profile=profile)


def _get_power_profile() -> PowerProfileResponse:
    stdout, stderr, code = _run_command(["powerprofilesctl", "get"])
    if code != 0 or not stdout:
        raise HTTPException(status_code=500, detail=stderr or stdout or "failed to query power profile")
    return PowerProfileResponse(success=True, message="current power profile retrieved", profile=stdout.strip())


def _schedule_shutdown(at: datetime) -> ValueResponse:
    # Normalize incoming datetime to local naive time and compute minutes until shutdown.
    if at.tzinfo is not None:
        at_local = at.astimezone()  # convert to local timezone
        at_naive = at_local.replace(tzinfo=None)
    else:
        at_naive = at

    now = datetime.now()
    delta = at_naive - now
    secs = delta.total_seconds()
    if secs <= 0:
        raise HTTPException(status_code=400, detail="scheduled time must be in the future")

    # shutdown accepts relative minutes as +M; compute ceiling minutes
    minutes = int((secs + 59) // 60)
    if minutes <= 0:
        minutes = 1

    time_arg = f"+{minutes}"
    readable = at_naive.strftime("%Y-%m-%d %H:%M")
    return _power_action(["shutdown", "-h", time_arg], f"shutdown scheduled for {readable}")


def _cancel_scheduled_shutdown() -> ValueResponse:
    return _power_action(["shutdown", "-c"], "shutdown canceled")


@router.post("/shutdown", response_model=ValueResponse, dependencies=[Depends(get_current_user)])
async def shutdown() -> Any:
    """Shutdown the machine."""
    return _power_action(["systemctl", "poweroff"], "shutdown initiated")


@router.post("/restart", response_model=ValueResponse, dependencies=[Depends(get_current_user)])
async def restart() -> Any:
    """Restart the machine."""
    return _power_action(["systemctl", "reboot"], "restart initiated")


@router.post("/sleep", response_model=ValueResponse, dependencies=[Depends(get_current_user)])
async def sleep() -> Any:
    """Put the machine to sleep."""
    return _power_action(["systemctl", "suspend"], "sleep initiated")


@router.post("/hibernate", response_model=ValueResponse, dependencies=[Depends(get_current_user)])
async def hibernate() -> Any:
    """Hibernate the machine."""
    return _power_action(["systemctl", "hibernate"], "hibernate initiated")


@router.post("/schedule-shutdown", response_model=ValueResponse, dependencies=[Depends(get_current_user)])
async def schedule_shutdown(request: ScheduleShutdownRequest) -> Any:
    """Schedule a shutdown at the given ISO datetime."""
    return _schedule_shutdown(request.at)


@router.post("/cancel-shutdown", response_model=ValueResponse, dependencies=[Depends(get_current_user)])
async def cancel_shutdown() -> Any:
    """Cancel a pending scheduled shutdown."""
    return _cancel_scheduled_shutdown()


@router.get("/profile", response_model=PowerProfileResponse, dependencies=[Depends(get_current_user)])
async def get_power_profile() -> Any:
    """Get the current power profile."""
    return _get_power_profile()


@router.post("/profile", response_model=PowerProfileResponse, dependencies=[Depends(get_current_user)])
async def set_power_profile(request: PowerProfileRequest) -> Any:
    """Set the power profile."""
    return _power_profile_action(["powerprofilesctl", "set", request.profile], request.profile)
