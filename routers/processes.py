import getpass
import re
import subprocess
from pathlib import Path
from typing import Any, List, Optional

import psutil
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from dependencies import get_current_user

router = APIRouter(prefix="/processes", tags=["processes"])


def _run_command(cmd: list[str], timeout: int = 10) -> tuple[str, str, int]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        return "", str(exc), 1


class ProcessInfo(BaseModel):
    pid: int
    name: str
    cpu_percent: float
    memory_percent: float
    status: Optional[str]
    cmdline: List[str] = Field(default_factory=list)


class ProcessList(BaseModel):
    processes: List[ProcessInfo]


class LaunchRequest(BaseModel):
    command: str
    args: List[str] = Field(default_factory=list)


class ApplicationRequest(BaseModel):
    name: str
    args: List[str] = Field(default_factory=list)


class ApplicationCloseRequest(BaseModel):
    name: str


def _kill_processes_by_name(name: str) -> int:
    killed_count = 0
    for proc in psutil.process_iter(["name"]):
        try:
            if proc.info.get("name") and proc.info["name"].lower() == name.lower():
                proc.terminate()
                proc.wait(timeout=3)
                killed_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
            continue
    return killed_count


class ActionResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    pid: Optional[int] = None
    killed_count: Optional[int] = None


@router.get("", response_model=ProcessList, dependencies=[Depends(get_current_user)])
async def list_processes() -> Any:
    """List running processes with CPU and memory usage."""
    processes: List[ProcessInfo] = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "cmdline", "status"]):
        try:
            with proc.oneshot():
                processes.append(
                    ProcessInfo(
                        pid=proc.pid,
                        name=proc.info.get("name") or "",
                        cpu_percent=float(proc.info.get("cpu_percent", 0.0)) if proc.info.get("cpu_percent") is not None else 0.0,
                        memory_percent=float(proc.info.get("memory_percent", 0.0)) if proc.info.get("memory_percent") is not None else 0.0,
                        status=proc.info.get("status"),
                        cmdline=[str(item) for item in proc.info.get("cmdline", []) if item],
                    )
                )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return ProcessList(processes=sorted(processes, key=lambda item: item.cpu_percent, reverse=True))


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
    killed_count = _kill_processes_by_name(name)
    if killed_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No matching processes found")
    return ActionResponse(success=True, message=f"Killed {killed_count} process(es).", killed_count=killed_count)


@router.post("/launch", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def launch_process(request: LaunchRequest) -> Any:
    """Launch a new process with optional arguments."""
    try:
        proc = subprocess.Popen([request.command, *request.args])
        return ActionResponse(success=True, message="Process launched.", pid=proc.pid)
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Command not found")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/app/open", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def open_application(request: ApplicationRequest) -> Any:
    """Open an application by name with optional arguments."""
    try:
        proc = subprocess.Popen([request.name, *request.args])
        return ActionResponse(success=True, message="Application launched.", pid=proc.pid)
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/app/close", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def close_application(request: ApplicationCloseRequest) -> Any:
    """Close an application by process name."""
    killed_count = _kill_processes_by_name(request.name)
    if killed_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No matching application processes found")
    return ActionResponse(success=True, message=f"Closed {killed_count} process(es).", killed_count=killed_count)


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
    title, stderr, returncode = _run_command(["xdotool", "getwindowname", window_id])
    if returncode == 0 and title:
        return title

    for prop in ["_NET_WM_NAME", "WM_NAME"]:
        stdout, stderr_prop, rc_prop = _run_command(["xprop", "-id", window_id, prop])
        if rc_prop == 0 and stdout:
            parsed = _parse_xprop_title(stdout)
            if parsed:
                return parsed

    return "Untitled window"


def _get_window_app_path() -> str:
    """Get the absolute executable path of the active window's process."""
    stdout, stderr, returncode = _run_command(["xprop", "-root", "_NET_CLIENT_LIST_STACKING"])
    if returncode != 0 or not stdout:
        return ""
    
    window_ids = re.findall(r'0x[0-9a-fA-F]+', stdout)
    if not window_ids:
        return ""
    
    window_ids.reverse()
    
    for wid in window_ids:
        xwininfo_out, _, xwininfo_rc = _run_command(["xwininfo", "-id", wid])
        if xwininfo_rc != 0:
            continue
        
        if "Map State: IsViewable" not in xwininfo_out:
            continue
        
        if "Width: 1" in xwininfo_out or "Height: 1" in xwininfo_out:
            continue
        
        pid_out, _, pid_rc = _run_command(["xprop", "-id", wid, "_NET_WM_PID"])
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


class ActiveWindowResponse(BaseModel):
    window_id: str
    title: str
    app_name: Optional[str] = None


@router.get("/active-window", response_model=ActiveWindowResponse, dependencies=[Depends(get_current_user)])
async def active_window() -> Any:
    """Return the currently focused window title and app executable path."""
    stdout, stderr, returncode = _run_command(["xdotool", "getwindowfocus"])
    if returncode != 0 or not stdout:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or "Could not determine active window")
    window_id = stdout.strip()
    title = _get_window_title(window_id)
    app_path = _get_window_app_path()
    return ActiveWindowResponse(window_id=window_id, title=title, app_name=app_path or title)


@router.post("/window/minimize", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def minimize_window(request: WindowActionRequest) -> Any:
    """Minimize a window by window ID."""
    _, stderr, returncode = _run_command(["xdotool", "windowminimize", request.window_id])
    if returncode != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or "Could not minimize window")
    return ActionResponse(success=True, message="Window minimized.")


@router.post("/window/close", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def close_window(request: WindowActionRequest) -> Any:
    """Close a window by window ID."""
    _, stderr, returncode = _run_command(["xdotool", "windowclose", request.window_id])
    if returncode != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or "Could not close window")
    return ActionResponse(success=True, message="Window closed.")
