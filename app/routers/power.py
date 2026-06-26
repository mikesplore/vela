from typing import Any

from fastapi import APIRouter, Depends
from app.dependencies import get_current_user
from app.domain.display import ValueResponse
from app.domain.power import ScheduleShutdownRequest, PowerProfileResponse, PowerProfileRequest
from app.services.power import power_action, power_profile_action, cancel_scheduled_shutdown, get_power_profile as get_p_p

router = APIRouter(prefix="/power", tags=["power"])


@router.post("/shutdown", response_model=ValueResponse, dependencies=[Depends(get_current_user)])
async def shutdown() -> Any:
    """Shutdown the machine."""
    return power_action(["systemctl", "poweroff"], "shutdown initiated")


@router.post("/restart", response_model=ValueResponse, dependencies=[Depends(get_current_user)])
async def restart() -> Any:
    """Restart the machine."""
    return power_action(["systemctl", "reboot"], "restart initiated")


@router.post("/sleep", response_model=ValueResponse, dependencies=[Depends(get_current_user)])
async def sleep() -> Any:
    """Put the machine to sleep."""
    return power_action(["systemctl", "suspend"], "sleep initiated")


@router.post("/hibernate", response_model=ValueResponse, dependencies=[Depends(get_current_user)])
async def hibernate() -> Any:
    """Hibernate the machine."""
    return power_action(["systemctl", "hibernate"], "hibernate initiated")


@router.post("/schedule-shutdown", response_model=ValueResponse, dependencies=[Depends(get_current_user)])
async def schedule_shutdown(request: ScheduleShutdownRequest) -> Any:
    """Schedule a shutdown at the given ISO datetime."""
    return schedule_shutdown(request.at)


@router.post("/cancel-shutdown", response_model=ValueResponse, dependencies=[Depends(get_current_user)])
async def cancel_shutdown() -> Any:
    """Cancel a pending scheduled shutdown."""
    return cancel_scheduled_shutdown()


@router.get("/profile", response_model=PowerProfileResponse, dependencies=[Depends(get_current_user)])
async def get_power_profile() -> Any:
    """Get the current power profile."""
    return get_p_p()


@router.post("/profile", response_model=PowerProfileResponse, dependencies=[Depends(get_current_user)])
async def set_power_profile(request: PowerProfileRequest) -> Any:
    """Set the power profile."""
    return power_profile_action(["powerprofilesctl", "set", request.profile], request.profile)
