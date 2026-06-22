import base64
import getpass
import os
import re
import subprocess
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.dependencies import get_current_user

router = APIRouter(prefix="/security", tags=["security"])


def _run_command(cmd: list[str], timeout: int = 10) -> tuple[str, str, int]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        return "", str(exc), 1


def _run_command_bytes(cmd: list[str], timeout: int = 10) -> tuple[bytes, str, int]:
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
        stderr = result.stderr.decode(errors="ignore") if result.stderr else ""
        return result.stdout, stderr.strip(), result.returncode
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        return b"", str(exc), 1


def _parse_session_ids(raw: str) -> List[str]:
    return [item for item in re.split(r"\s+", raw.strip()) if item]


def _get_user_session_ids(username: str) -> List[str]:
    stdout, stderr, returncode = _run_command(["loginctl", "show-user", username, "--property=Sessions", "--value"])
    if returncode != 0 or not stdout:
        return []
    return _parse_session_ids(stdout)


def _lock_session(session_id: str) -> tuple[bool, str]:
    _, stderr, returncode = _run_command(["loginctl", "lock-session", session_id])
    return returncode == 0, stderr


def _lock_screen_with_fallback() -> tuple[bool, str]:
    # Try screensaver commands first (no permission dialog)
    screensaver_commands = [
        ["gnome-screensaver-command", "-l"],
        ["xdg-screensaver", "lock"],
        ["dm-tool", "lock"],
    ]
    stderr = ""
    for cmd in screensaver_commands:
        _, stderr2, rc = _run_command(cmd)
        if rc == 0:
            return True, " ".join(cmd)
        stderr = stderr or stderr2

    # Fallback to loginctl (may show permission dialog after system updates)
    _, stderr2, returncode = _run_command(["loginctl", "lock-sessions"])
    if returncode == 0:
        return True, "loginctl lock-sessions"
    stderr = stderr or stderr2

    username = getpass.getuser()
    for session_id in _get_user_session_ids(username):
        success, session_err = _lock_session(session_id)
        if success:
            return True, f"loginctl lock-session {session_id}"
        stderr = stderr or session_err

    session_id = os.environ.get("XDG_SESSION_ID")
    if session_id:
        success, session_err = _lock_session(session_id)
        if success:
            return True, f"loginctl lock-session {session_id}"
        stderr = stderr or session_err

    return False, stderr or "Could not lock screen"


class ActionResponse(BaseModel):
    success: bool
    message: Optional[str] = None


class WebcamSnapshotResponse(BaseModel):
    image_base64: str


class LoginEvent(BaseModel):
    raw_line: str


class LoginHistoryResponse(BaseModel):
    events: List[LoginEvent]


class SSHSession(BaseModel):
    user: str
    tty: str
    host: Optional[str]
    login_time: Optional[str]


class SSHSessionsResponse(BaseModel):
    sessions: List[SSHSession]


@router.post("/lock", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def lock_screen() -> Any:
    """Lock the screen session."""
    success, source = _lock_screen_with_fallback()
    if not success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=source)
    return ActionResponse(success=True, message=f"Screen locked via {source}.")


@router.post("/logout", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def logout_user() -> Any:
    """Log out the current user session."""
    username = getpass.getuser()
    _, stderr, returncode = _run_command(["loginctl", "terminate-user", username])
    if returncode != 0:
        _, stderr_kill, returncode_kill = _run_command(["pkill", "-KILL", "-u", username])
        if returncode_kill != 0:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or stderr_kill or "Could not log out user")
    return ActionResponse(success=True, message="User logged out.")


@router.post("/webcam/disable", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def disable_webcam() -> Any:
    """Unload the webcam kernel module."""
    _, stderr, returncode = _run_command(["modprobe", "-r", "uvcvideo"])
    if returncode != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or "Could not disable webcam")
    return ActionResponse(success=True, message="Webcam disabled.")


@router.post("/webcam/enable", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def enable_webcam() -> Any:
    """Load the webcam kernel module."""
    _, stderr, returncode = _run_command(["modprobe", "uvcvideo"])
    if returncode != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or "Could not enable webcam")
    return ActionResponse(success=True, message="Webcam enabled.")


@router.post("/webcam/snapshot", response_model=WebcamSnapshotResponse, dependencies=[Depends(get_current_user)])
async def webcam_snapshot() -> Any:
    """Capture a webcam image from /dev/video0 and return it as base64."""
    stdout, stderr, returncode = _run_command_bytes(
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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or "Could not capture webcam image")
    return WebcamSnapshotResponse(image_base64=base64.b64encode(stdout).decode())


@router.post("/mic/disable", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def disable_mic() -> Any:
    """Mute the default microphone source."""
    _, stderr, returncode = _run_command(["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "1"])
    if returncode != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or "Could not disable microphone")
    return ActionResponse(success=True, message="Microphone disabled.")


@router.post("/mic/enable", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def enable_mic() -> Any:
    """Unmute the default microphone source."""
    _, stderr, returncode = _run_command(["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "0"])
    if returncode != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or "Could not enable microphone")
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
    stdout, stderr, returncode = _run_command(["last", "-n", "20"])
    if returncode != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or "Could not read login history")
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
    stdout, stderr, returncode = _run_command(["who"])
    if returncode != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or "Could not list SSH sessions")
    return SSHSessionsResponse(sessions=_parse_ssh_sessions(stdout))
