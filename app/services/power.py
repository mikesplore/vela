from datetime import datetime
from typing import List

from fastapi import HTTPException

from app.domain.display import ValueResponse
from app.domain.power import PowerProfileResponse
from app.utils.run_command import run_command


def power_action(cmd: List[str], success_message: str) -> ValueResponse:
    stdout, stderr, code = run_command(cmd)
    if code != 0:
        raise HTTPException(status_code=500, detail=stderr or stdout or "power action failed")
    return ValueResponse(success=True, message=success_message)


def power_profile_action(cmd: List[str], profile: str) -> PowerProfileResponse:
    stdout, stderr, code = run_command(cmd)
    if code != 0:
        raise HTTPException(status_code=500, detail=stderr or stdout or "power profile action failed")
    return PowerProfileResponse(success=True, message=f"profile set to {profile}", profile=profile)


def get_power_profile() -> PowerProfileResponse:
    stdout, stderr, code = run_command(["powerprofilesctl", "get"])
    if code != 0 or not stdout:
        raise HTTPException(status_code=500, detail=stderr or stdout or "failed to query power profile")
    return PowerProfileResponse(success=True, message="current power profile retrieved", profile=stdout.strip())


def schedule_shutdown(at: datetime) -> ValueResponse:
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
    return power_action(["shutdown", "-h", time_arg], f"shutdown scheduled for {readable}")


def cancel_scheduled_shutdown() -> ValueResponse:
    return power_action(["shutdown", "-c"], "shutdown canceled")
