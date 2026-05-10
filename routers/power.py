import subprocess
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dependencies import get_current_user

router = APIRouter(prefix="/power", tags=["power"])


class ValueResponse(BaseModel):
    success: bool
    message: str


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
