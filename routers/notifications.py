import re
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dependencies import get_current_user

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _run_command(cmd: list[str], timeout: int = 10) -> tuple[str, str, int]:
    try:
        import subprocess

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        return "", str(exc), 1


class NotificationRequest(BaseModel):
    title: str
    message: str
    app_name: Optional[str] = None
    urgency: Optional[str] = Field(None, pattern="^(low|normal|critical)$")


class NotificationRecord(BaseModel):
    id: int
    title: str
    message: str
    app_name: Optional[str]
    urgency: Optional[str]
    timestamp: float


class NotificationList(BaseModel):
    notifications: List[NotificationRecord]


_notifications: List[NotificationRecord] = []
_next_notification_id = 1


def _send_notification(request: NotificationRequest) -> None:
    # Try notify-send first (standard CLI notification helper)
    args = ["notify-send", request.title, request.message]
    if request.app_name:
        args.extend(["-a", request.app_name])
    if request.urgency:
        args.extend(["-u", request.urgency])

    stdout, stderr, returncode = _run_command(args)
    if returncode == 0:
        return

    # CLI failed — try Python notification libraries as a fallback.
    # First try notify2 (dbus bindings common on Linux)
    try:
        import notify2

        notify2.init(request.app_name or "Vela")
        n = notify2.Notification(request.title, request.message)
        # Map urgency if provided
        if request.urgency == "low":
            n.set_urgency(notify2.URGENCY_LOW)
        elif request.urgency == "critical":
            n.set_urgency(notify2.URGENCY_CRITICAL)
        else:
            n.set_urgency(notify2.URGENCY_NORMAL)
        n.show()
        return
    except Exception:
        pass

    # Next try GObject Introspection Notify (pygobject)
    try:
        from gi.repository import Notify

        Notify.init(request.app_name or "Vela")
        n = Notify.Notification.new(request.title, request.message)
        n.show()
        return
    except Exception:
        pass

    # All attempts failed — raise to allow caller to handle reporting
    raise RuntimeError(f"Failed to send notification: {stderr or 'unknown error'}")


def _clear_notifications() -> None:
    _run_command(["dunstctl", "close-all"])


def _parse_dunst_history(raw_history: str) -> List[NotificationRecord]:
    notifications: List[NotificationRecord] = []
    for line in raw_history.splitlines():
        line = line.strip()
        if not line:
            continue

        match = re.match(
            r'^\[?(?P<id>\d+)\]?\s+(?P<app>[^\s]+)\s+"(?P<title>[^"]+)"\s+"(?P<message>[^"]+)"',
            line,
        )
        if match:
            notifications.append(
                NotificationRecord(
                    id=int(match.group("id")),
                    title=match.group("title"),
                    message=match.group("message"),
                    app_name=match.group("app"),
                    urgency=None,
                    timestamp=time.time(),
                )
            )
            continue

        # Fallback: preserve the raw line as notification text.
        notifications.append(
            NotificationRecord(
                id=len(notifications) + 1,
                title=line[:80],
                message=line,
                app_name=None,
                urgency=None,
                timestamp=time.time(),
            )
        )
    return notifications


def _list_system_notifications() -> List[NotificationRecord]:
    stdout, stderr, returncode = _run_command(["dunstctl", "history"])
    if returncode != 0 or not stdout:
        return list(_notifications)
    return _parse_dunst_history(stdout)


@router.post("/send", response_model=NotificationRecord, dependencies=[Depends(get_current_user)])
async def send_notification(request: NotificationRequest) -> Any:
    """Send a desktop notification and retain it in the agent history."""
    global _next_notification_id
    try:
        _send_notification(request)
    except Exception as exc:
        # Surface a clear error to the client when notifications can't be delivered
        raise HTTPException(status_code=500, detail=f"Notification failed: {exc}")
    record = NotificationRecord(
        id=_next_notification_id,
        title=request.title,
        message=request.message,
        app_name=request.app_name,
        urgency=request.urgency,
        timestamp=time.time(),
    )
    _notifications.append(record)
    _next_notification_id += 1
    return record


@router.post("/clear", response_model=Dict[str, bool], dependencies=[Depends(get_current_user)])
async def clear_notifications() -> Any:
    """Clear agent-tracked notifications and attempt to close desktop notifications."""
    _notifications.clear()
    _clear_notifications()
    return {"success": True}


@router.get("/read", response_model=NotificationList, dependencies=[Depends(get_current_user)])
async def read_notifications() -> Any:
    """Read notifications that were sent through this agent."""
    return NotificationList(notifications=_notifications)


@router.get("/list", response_model=NotificationList, dependencies=[Depends(get_current_user)])
async def list_notifications() -> Any:
    """List desktop notification history or agent-tracked notifications."""
    return NotificationList(notifications=_list_system_notifications())
