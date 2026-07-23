import shutil
from pathlib import Path
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import get_current_user
from app.domain.audio import ActionResponse
from app.domain.maintenance import (
    BootErrorsResponse,
    LogResponse,
    PackageInstalledResponse,
    ServiceListResponse,
    ServiceStatusResponse,
    TimerListResponse,
    UpdateEntry,
    UpdateResponse,
)
from app.services.maintenance import (
    detect_package_manager,
    get_boot_errors,
    get_service_status,
    is_package_installed,
    list_failed_services,
    list_systemd_services,
    list_systemd_timers,
    service_action,
)
from app.utils.run_command import run_command

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


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
    stdout, stderr, rc = run_command(["journalctl", "-u", service, f"-n", str(lines), "--no-pager"])
    if rc != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=stderr or "Could not read service logs")
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
    manager = detect_package_manager()
    if manager == "apt":
        stdout, stderr, rc = run_command(["apt", "list", "--upgradable"])
        if rc != 0:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail=stderr or "Could not check updates")
        updates = _parse_apt_updates(stdout)
    elif manager == "dnf":
        stdout, stderr, rc = run_command(["dnf", "check-update"])
        if rc not in (0, 100):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail=stderr or "Could not check updates")
        updates = _parse_apt_updates(stdout)
    elif manager == "pacman":
        stdout, stderr, rc = run_command(["pacman", "-Qu"])
        if rc != 0:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail=stderr or "Could not check updates")
        updates = _parse_pacman_updates(stdout)
    else:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unsupported package manager")
    return UpdateResponse(manager=manager or "unknown", updates=updates)


@router.post("/update", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def run_update(confirm: bool = Query(False)) -> Any:
    """Run a full system update when explicitly confirmed."""
    if not confirm:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Confirmation required to run updates")
    manager = detect_package_manager()
    if manager == "apt":
        stdout, stderr, rc = run_command(["apt-get", "update"])
        if rc != 0:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail=stderr or stdout or "Could not refresh apt cache")
        stdout, stderr, rc = run_command(["apt-get", "upgrade", "-y"])
    elif manager == "dnf":
        stdout, stderr, rc = run_command(["dnf", "upgrade", "-y"])
    elif manager == "pacman":
        stdout, stderr, rc = run_command(["pacman", "-Syu", "--noconfirm"])
    else:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unsupported package manager")
    if rc != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=stderr or stdout or "Update failed")
    return ActionResponse(success=True, message="System updated.")


@router.post("/sync-time", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def sync_time() -> Any:
    """Sync the system clock via NTP."""
    stdout, stderr, rc = run_command(["timedatectl", "set-ntp", "true"])
    if rc != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=stderr or stdout or "Could not sync time")
    return ActionResponse(success=True, message="Time synchronization enabled.")


@router.get("/services", response_model=ServiceListResponse, dependencies=[Depends(get_current_user)])
async def list_services(
    filter: str | None = Query(None, description="Filter by service name or description"),
    scope: str = Query("system", pattern="^(system|user|all)$"),
) -> Any:
    """List systemd services and their status."""
    services, error = list_systemd_services(filter_text=filter, scope=scope)
    if error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error)
    return ServiceListResponse(services=services)


@router.get("/service/status", response_model=ServiceStatusResponse, dependencies=[Depends(get_current_user)])
async def service_status(
    name: str = Query(...),
    scope: str = Query("all", pattern="^(system|user|all)$"),
) -> Any:
    """Get status for a single systemd service."""
    status_info, error = get_service_status(name, scope=scope)
    if error or not status_info:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error or "Service not found")
    return status_info


@router.get("/services/failed", response_model=ServiceListResponse, dependencies=[Depends(get_current_user)])
async def failed_services(scope: str = Query("system", pattern="^(system|user|all)$")) -> Any:
    """List failed systemd units."""
    services, error = list_failed_services(scope=scope)
    if error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error)
    return ServiceListResponse(services=services)


@router.get("/timers", response_model=TimerListResponse, dependencies=[Depends(get_current_user)])
async def list_timers(
    filter: str | None = Query(None, description="Filter by timer name or description"),
    scope: str = Query("system", pattern="^(system|user|all)$"),
) -> Any:
    """List systemd timers."""
    timers, error = list_systemd_timers(filter_text=filter, scope=scope)
    if error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error)
    return TimerListResponse(timers=timers)


@router.get("/package-installed", response_model=PackageInstalledResponse, dependencies=[Depends(get_current_user)])
async def package_installed(name: str = Query(...)) -> Any:
    """Check whether a package is installed."""
    return is_package_installed(name)


@router.get("/boot-errors", response_model=BootErrorsResponse, dependencies=[Depends(get_current_user)])
async def boot_errors(lines: int = Query(50, ge=1, le=500)) -> Any:
    """Return recent error-level journal entries from the current boot."""
    return get_boot_errors(lines=lines)


@router.post("/service/restart", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def restart_service(
    name: str = Query(...),
    scope: str = Query("all", pattern="^(system|user|all)$"),
) -> Any:
    """Restart a systemd service."""
    response, error = service_action(name, "restart", scope=scope)
    if error and not response.success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error)
    return response


@router.post("/service/stop", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def stop_service(
    name: str = Query(...),
    scope: str = Query("all", pattern="^(system|user|all)$"),
) -> Any:
    """Stop a systemd service."""
    response, error = service_action(name, "stop", scope=scope)
    if error and not response.success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error)
    return response


@router.post("/service/start", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def start_service(
    name: str = Query(...),
    scope: str = Query("all", pattern="^(system|user|all)$"),
) -> Any:
    """Start a systemd service."""
    response, error = service_action(name, "start", scope=scope)
    if error and not response.success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error)
    return response
