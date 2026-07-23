import re
import subprocess
from pathlib import Path
from typing import Any, List, Optional

import psutil
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.dependencies import get_current_user
from app.domain.processes import (
    ProcessInfo,
    ProcessList,
    ActionResponse,
    LaunchRequest,
    ApplicationRequest,
    ApplicationCloseRequest,
    ProcessRunningResponse,
    InstalledApplicationList,
)
from app.services.processes import (
    ApplicationLaunchError,
    ApplicationNotFoundError,
    ApplicationNotRunningError,
    kill_processes_by_name as kill_processes_by_name_svc,
    is_process_running as is_process_running_svc,
    list_installed_applications as list_installed_applications_svc,
    open_installed_application,
    close_installed_application,
    spawn_detached,
)
from app.utils.run_command import run_command

router = APIRouter(prefix="/processes", tags=["processes"])


@router.get("", response_model=ProcessList, dependencies=[Depends(get_current_user)])
async def list_processes() -> Any:
    """List running processes with CPU and memory usage."""
    processes: List[ProcessInfo] = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "cmdline", "status"]):
        try:
            with proc.oneshot():
                # Safely capture cmdline to avoid NoneType iteration errors
                raw_cmdline = proc.info.get("cmdline")
                cmdline_list = [str(item) for item in raw_cmdline if item] if raw_cmdline else []

                processes.append(
                    ProcessInfo(
                        pid=proc.pid,
                        name=proc.info.get("name") or "Unknown",
                        cpu_percent=float(proc.info.get("cpu_percent", 0.0)) if proc.info.get(
                            "cpu_percent") is not None else 0.0,
                        memory_percent=float(proc.info.get("memory_percent", 0.0)) if proc.info.get(
                            "memory_percent") is not None else 0.0,
                        status=proc.info.get("status"),
                        cmdline=cmdline_list,
                    )
                )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return ProcessList(processes=sorted(processes, key=lambda item: item.cpu_percent, reverse=True))


@router.get("/apps", response_model=InstalledApplicationList, dependencies=[Depends(get_current_user)])
async def list_applications(filter: str | None = None) -> Any:
    """List installed desktop applications from .desktop entries."""
    return list_installed_applications_svc(filter_text=filter)


@router.get("/running/{name}", response_model=ProcessRunningResponse, dependencies=[Depends(get_current_user)])
async def process_running(name: str) -> Any:
    """Check whether a process is currently running by name."""
    running, count, pids = is_process_running_svc(name)
    return ProcessRunningResponse(name=name, running=running, count=count, pids=pids)


@router.delete("/{pid}", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def kill_process(pid: int) -> Any:
    """Terminate a process by PID."""
    try:
        process = psutil.Process(pid)
        process.terminate()
        process.wait(timeout=3)
        return ActionResponse(success=True, message=f"Process {pid} terminated.")
    except psutil.NoSuchProcess:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Process not found")
    except psutil.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)
        return ActionResponse(success=True, message=f"Process {pid} killed after timeout.")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.delete("/name/{name}", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def kill_processes_by_name(name: str) -> Any:
    """Terminate all processes matching a name."""
    killed_count = kill_processes_by_name_svc(name)

    # Dynamic message based on whether anything was actually terminated
    if killed_count > 0:
        message = f"Killed {killed_count} process(es)."
    else:
        message = "No matching processes found; 0 processes killed."

    # Always return a successful 200 OK status containing the count
    return ActionResponse(
        success=True,
        message=message,
        killed_count=killed_count
    )


@router.post("/launch", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def launch_process(request: LaunchRequest) -> Any:
    """Launch a process detached from the Vela service cgroup when possible."""
    try:
        result = spawn_detached([request.command, *request.args])
        return ActionResponse(success=True, message=result.message, pid=result.pid)
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Command not found")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/app/open", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def open_application(request: ApplicationRequest) -> Any:
    """Open an application by friendly name, .desktop id, or exec binary."""
    try:
        result = open_installed_application(request.name, request.args)
        return ActionResponse(
            success=True,
            message=result.message,
            pid=result.pid,
            application_id=result.application_id,
            application_name=result.application_name,
        )
    except ApplicationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ApplicationLaunchError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/app/close", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def close_application(request: ApplicationCloseRequest) -> Any:
    """Close an application by friendly name, .desktop id, or process name."""
    try:
        killed_count, application_id, application_name = close_installed_application(request.name)
        label = application_name or request.name
        return ActionResponse(
            success=True,
            message=f"Closed {killed_count} process(es) for {label}.",
            killed_count=killed_count,
            application_id=application_id,
            application_name=application_name,
        )
    except ApplicationNotRunningError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


class WindowActionRequest(BaseModel):
    window_id: str


class ActiveWindowResponse(BaseModel):
    window_id: str
    title: str


def _parse_xprop_title(raw: str) -> str:
    for line in raw.splitlines():
        if "_NET_WM_NAME" in line or "WM_NAME" in line:
            parts = line.split("=", 1)
            if len(parts) == 2:
                value = parts[1].strip().strip('"')
                if value and value.lower() != "(null)":
                    return value
    return ""


def _parse_xprop_class(raw: str) -> str:
    for line in raw.splitlines():
        if "WM_CLASS" in line or "_NET_WM_CLASS" in line:
            values = re.findall(r'"([^"]+)"', line)
            if values:
                class_name = values[-1].strip()
                if class_name and class_name.lower() != "(null)":
                    return class_name
    return ""


def _get_window_title(window_id: str) -> str:
    title, stderr, returncode = run_command(["xdotool", "getwindowname", window_id])
    if returncode == 0 and title:
        return title

    for prop in ["_NET_WM_NAME", "WM_NAME"]:
        stdout, stderr_prop, rc_prop = run_command(["xprop", "-id", window_id, prop])
        if rc_prop == 0 and stdout:
            parsed = _parse_xprop_title(stdout)
            if parsed:
                return parsed

    return "Untitled window"


def _get_window_app_path() -> str:
    """Get the absolute executable path of the active window's process."""
    stdout, stderr, returncode = run_command(["xprop", "-root", "_NET_CLIENT_LIST_STACKING"])
    if returncode != 0 or not stdout:
        return ""

    window_ids = re.findall(r'0x[0-9a-fA-F]+', stdout)
    if not window_ids:
        return ""

    window_ids.reverse()

    for wid in window_ids:
        xwininfo_out, _, xwininfo_rc = run_command(["xwininfo", "-id", wid])
        if xwininfo_rc != 0:
            continue

        if "Map State: IsViewable" not in xwininfo_out:
            continue

        if "Width: 1" in xwininfo_out or "Height: 1" in xwininfo_out:
            continue

        pid_out, _, pid_rc = run_command(["xprop", "-id", wid, "_NET_WM_PID"])
        if pid_rc != 0:
            continue

        pid_match = re.search(r'\d+', pid_out)
        if not pid_match:
            continue

        pid = pid_match.group()
        proc_path = f"/proc/{pid}/exe"

        try:
            if Path(proc_path).exists():
                return str(Path(proc_path).resolve())
        except (OSError, Exception):
            continue

    return ""



@router.get("/active-window", response_model=ActiveWindowResponse, dependencies=[Depends(get_current_user)])
async def active_window() -> Any:
    """Return the currently focused window title and app executable path."""
    stdout, stderr, returncode = run_command(["xdotool", "getwindowfocus"])
    if returncode != 0 or not stdout:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=stderr or "Could not determine active window")
    window_id = stdout.strip()
    title = _get_window_title(window_id)
    app_path = _get_window_app_path()
    return ActiveWindowResponse(window_id=window_id, title=title, app_name=app_path or title)


@router.post("/window/minimize", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def minimize_window(request: WindowActionRequest) -> Any:
    """Minimize a window by window ID."""
    _, stderr, returncode = run_command(["xdotool", "windowminimize", request.window_id])
    if returncode != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=stderr or "Could not minimize window")
    return ActionResponse(success=True, message="Window minimized.")


@router.post("/window/close", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def close_window(request: WindowActionRequest) -> Any:
    """Close a window by window ID."""
    _, stderr, returncode = run_command(["xdotool", "windowclose", request.window_id])
    if returncode != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=stderr or "Could not close window")
    return ActionResponse(success=True, message="Window closed.")
