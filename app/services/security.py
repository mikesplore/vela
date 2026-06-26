import getpass
import os
import re
import subprocess
from typing import List, Optional

from pydantic import BaseModel

from utils.run_command import run_command


def run_command_bytes(cmd: list[str], timeout: int = 10) -> tuple[bytes, str, int]:
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
        stderr = result.stderr.decode(errors="ignore") if result.stderr else ""
        return result.stdout, stderr.strip(), result.returncode
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        return b"", str(exc), 1


def parse_session_ids(raw: str) -> List[str]:
    return [item for item in re.split(r"\s+", raw.strip()) if item]


def get_user_session_ids(username: str) -> List[str]:
    stdout, stderr, returncode = run_command(["loginctl", "show-user", username, "--property=Sessions", "--value"])
    if returncode != 0 or not stdout:
        return []
    return parse_session_ids(stdout)


def lock_session(session_id: str) -> tuple[bool, str]:
    _, stderr, returncode = run_command(["loginctl", "lock-session", session_id])
    return returncode == 0, stderr


def lock_screen_with_fallback() -> tuple[bool, str]:
    # Try screensaver commands first (no permission dialog)
    screensaver_commands = [
        ["gnome-screensaver-command", "-l"],
        ["xdg-screensaver", "lock"],
        ["dm-tool", "lock"],
    ]
    stderr = ""
    for cmd in screensaver_commands:
        _, stderr2, rc = run_command(cmd)
        if rc == 0:
            return True, " ".join(cmd)
        stderr = stderr or stderr2

    # Fallback to loginctl (may show permission dialog after system updates)
    _, stderr2, returncode = run_command(["loginctl", "lock-sessions"])
    if returncode == 0:
        return True, "loginctl lock-sessions"
    stderr = stderr or stderr2

    username = getpass.getuser()
    for session_id in get_user_session_ids(username):
        success, session_err = lock_session(session_id)
        if success:
            return True, f"loginctl lock-session {session_id}"
        stderr = stderr or session_err

    session_id = os.environ.get("XDG_SESSION_ID")
    if session_id:
        success, session_err = lock_session(session_id)
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
