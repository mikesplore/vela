import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from dependencies import get_current_user

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


def _run_command(cmd: list[str], timeout: int = 10) -> tuple[str, str, int]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        return "", str(exc), 1


def _detect_package_manager() -> Optional[str]:
    if shutil.which("apt-get"):
        return "apt"
    if shutil.which("dnf"):
        return "dnf"
    if shutil.which("pacman"):
        return "pacman"
    return None


class ServiceEntry(BaseModel):
    name: str
    load: str
    active: str
    sub: str
    description: str


class ServiceListResponse(BaseModel):
    services: List[ServiceEntry]


class UpdateEntry(BaseModel):
    package: str
    current: Optional[str] = None
    available: Optional[str] = None


class UpdateResponse(BaseModel):
    updates: List[UpdateEntry]
    manager: str


class ActionResponse(BaseModel):
    success: bool
    message: str


class LogResponse(BaseModel):
    service: str
    lines: List[str]


@router.post("/clear-cache", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def clear_cache() -> Any:
    """Clear /tmp and the user's cache directories."""
    errors: List[str] = []
    for path in [Path("/tmp"), Path.home() / ".cache"]:
        if not path.exists():
            continue
        for child in path.iterdir():
            try:
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            except OSError as exc:
                errors.append(str(exc))
    if errors:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="; ".join(errors))
    return ActionResponse(success=True, message="Cache cleared.")


@router.get("/logs", response_model=LogResponse, dependencies=[Depends(get_current_user)])
async def get_logs(service: str = Query(...), lines: int = Query(100, ge=1, le=1000)) -> Any:
    """Get the last N lines of a systemd service log."""
    stdout, stderr, rc = _run_command(["journalctl", "-u", service, f"-n", str(lines), "--no-pager"])
    if rc != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or "Could not read service logs")
    return LogResponse(service=service, lines=stdout.splitlines())


def _parse_apt_updates(raw: str) -> List[UpdateEntry]:
    updates: List[UpdateEntry] = []
    for line in raw.splitlines():
        if "/" in line and "upgradable" not in line:
            parts = line.split()
            if len(parts) >= 2:
                updates.append(UpdateEntry(package=parts[0], current=None, available=None))
    return updates


def _parse_pacman_updates(raw: str) -> List[UpdateEntry]:
    updates: List[UpdateEntry] = []
    for line in raw.splitlines():
        if line.strip() and "->" in line:
            package, available = line.split("->", 1)
            updates.append(UpdateEntry(package=package.strip(), available=available.strip()))
    return updates


@router.get("/updates", response_model=UpdateResponse, dependencies=[Depends(get_current_user)])
async def check_updates() -> Any:
    """Check for available system updates."""
    manager = _detect_package_manager()
    if manager == "apt":
        stdout, stderr, rc = _run_command(["apt", "list", "--upgradable"])
        if rc != 0:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or "Could not check updates")
        updates = _parse_apt_updates(stdout)
    elif manager == "dnf":
        stdout, stderr, rc = _run_command(["dnf", "check-update"])
        if rc not in (0, 100):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or "Could not check updates")
        updates = _parse_apt_updates(stdout)
    elif manager == "pacman":
        stdout, stderr, rc = _run_command(["pacman", "-Qu"])
        if rc != 0:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or "Could not check updates")
        updates = _parse_pacman_updates(stdout)
    else:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unsupported package manager")
    return UpdateResponse(manager=manager or "unknown", updates=updates)


@router.post("/update", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def run_update(confirm: bool = Query(False)) -> Any:
    """Run a full system update when explicitly confirmed."""
    if not confirm:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Confirmation required to run updates")
    manager = _detect_package_manager()
    if manager == "apt":
        stdout, stderr, rc = _run_command(["apt-get", "update"])
        if rc != 0:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or stdout or "Could not refresh apt cache")
        stdout, stderr, rc = _run_command(["apt-get", "upgrade", "-y"])
    elif manager == "dnf":
        stdout, stderr, rc = _run_command(["dnf", "upgrade", "-y"])
    elif manager == "pacman":
        stdout, stderr, rc = _run_command(["pacman", "-Syu", "--noconfirm"])
    else:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unsupported package manager")
    if rc != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or stdout or "Update failed")
    return ActionResponse(success=True, message="System updated.")


@router.post("/sync-time", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def sync_time() -> Any:
    """Sync the system clock via NTP."""
    stdout, stderr, rc = _run_command(["timedatectl", "set-ntp", "true"])
    if rc != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or stdout or "Could not sync time")
    return ActionResponse(success=True, message="Time synchronization enabled.")


@router.get("/services", response_model=ServiceListResponse, dependencies=[Depends(get_current_user)])
async def list_services() -> Any:
    """List systemd services and their status."""
    stdout, stderr, rc = _run_command(["systemctl", "list-units", "--type=service", "--all", "--no-legend", "--no-pager"])
    if rc != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or "Could not list services")
    services: List[ServiceEntry] = []
    for line in stdout.splitlines():
        parts = re.split(r"\s+", line, maxsplit=4)
        if len(parts) == 5:
            services.append(ServiceEntry(name=parts[0], load=parts[1], active=parts[2], sub=parts[3], description=parts[4]))
    return ServiceListResponse(services=services)


def _service_action(name: str, action: str) -> ActionResponse:
    stdout, stderr, rc = _run_command(["systemctl", action, name])
    if rc != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or stdout or f"Could not {action} service")
    return ActionResponse(success=True, message=f"Service {name} {action}ed.")


@router.post("/service/restart", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def restart_service(name: str = Query(...)) -> Any:
    """Restart a systemd service."""
    return _service_action(name, "restart")


@router.post("/service/stop", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def stop_service(name: str = Query(...)) -> Any:
    """Stop a systemd service."""
    return _service_action(name, "stop")


@router.post("/service/start", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def start_service(name: str = Query(...)) -> Any:
    """Start a systemd service."""
    return _service_action(name, "start")
