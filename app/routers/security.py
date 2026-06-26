import base64
import getpass
import re
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_current_user
from domain.audio import ActionResponse
from services.security import lock_screen_with_fallback, WebcamSnapshotResponse, run_command_bytes, LoginEvent, \
    LoginHistoryResponse, SSHSession, SSHSessionsResponse
from utils.run_command import run_command

router = APIRouter(prefix="/security", tags=["security"])


@router.post("/lock", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def lock_screen() -> Any:
    """Lock the screen session."""
    success, source = lock_screen_with_fallback()
    if not success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=source)
    return ActionResponse(success=True, message=f"Screen locked via {source}.")


@router.post("/logout", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def logout_user() -> Any:
    """Log out the current user session."""
    username = getpass.getuser()
    _, stderr, returncode = run_command(["loginctl", "terminate-user", username])
    if returncode != 0:
        _, stderr_kill, returncode_kill = run_command(["pkill", "-KILL", "-u", username])
        if returncode_kill != 0:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail=stderr or stderr_kill or "Could not log out user")
    return ActionResponse(success=True, message="User logged out.")


@router.post("/webcam/disable", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def disable_webcam() -> Any:
    """Unload the webcam kernel module."""
    _, stderr, returncode = run_command(["modprobe", "-r", "uvcvideo"])
    if returncode != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=stderr or "Could not disable webcam")
    return ActionResponse(success=True, message="Webcam disabled.")


@router.post("/webcam/enable", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def enable_webcam() -> Any:
    """Load the webcam kernel module."""
    _, stderr, returncode = run_command(["modprobe", "uvcvideo"])
    if returncode != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=stderr or "Could not enable webcam")
    return ActionResponse(success=True, message="Webcam enabled.")


@router.post("/webcam/snapshot", response_model=WebcamSnapshotResponse, dependencies=[Depends(get_current_user)])
async def webcam_snapshot() -> Any:
    """Capture a webcam image from /dev/video0 and return it as base64."""
    stdout, stderr, returncode = run_command_bytes(
        [
            "ffmpeg",
            "-f",
            "video4linux2",
            "-i",
            "/dev/video0",
            "-frames:v",
            "1",
            "-vcodec",
            "png",
            "-",
        ],
        timeout=10,
    )
    if returncode != 0 or not stdout:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=stderr or "Could not capture webcam image")
    return WebcamSnapshotResponse(image_base64=base64.b64encode(stdout).decode())


@router.post("/mic/disable", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def disable_mic() -> Any:
    """Mute the default microphone source."""
    _, stderr, returncode = run_command(["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "1"])
    if returncode != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=stderr or "Could not disable microphone")
    return ActionResponse(success=True, message="Microphone disabled.")


@router.post("/mic/enable", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def enable_mic() -> Any:
    """Unmute the default microphone source."""
    _, stderr, returncode = run_command(["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "0"])
    if returncode != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=stderr or "Could not enable microphone")
    return ActionResponse(success=True, message="Microphone enabled.")


def _parse_login_history(raw: str) -> List[LoginEvent]:
    events: List[LoginEvent] = []
    for line in raw.splitlines():
        if not line.strip() or line.startswith("wtmp"):
            continue
        events.append(LoginEvent(raw_line=line.strip()))
    return events


@router.get("/login-history", response_model=LoginHistoryResponse, dependencies=[Depends(get_current_user)])
async def login_history() -> Any:
    """Return recent login events from the system auth logs."""
    stdout, stderr, returncode = run_command(["last", "-n", "20"])
    if returncode != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=stderr or "Could not read login history")
    return LoginHistoryResponse(events=_parse_login_history(stdout))


def _parse_ssh_sessions(raw: str) -> List[SSHSession]:
    sessions: List[SSHSession] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        user = parts[0]
        tty = parts[1]
        login_time = " ".join(parts[2:5])
        host = None
        match = re.search(r"\(([^)]+)\)", line)
        if match:
            host = match.group(1)
        sessions.append(SSHSession(user=user, tty=tty, host=host, login_time=login_time))
    return sessions


@router.get("/ssh-sessions", response_model=SSHSessionsResponse, dependencies=[Depends(get_current_user)])
async def ssh_sessions() -> Any:
    """List active SSH sessions."""
    stdout, stderr, returncode = run_command(["who"])
    if returncode != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=stderr or "Could not list SSH sessions")
    return SSHSessionsResponse(sessions=_parse_ssh_sessions(stdout))
