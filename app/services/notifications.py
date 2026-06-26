import re
import time
from typing import List

from app.domain.notifications import notifications
from app.domain.notifications import NotificationRecord, NotificationRequest
from app.services.system_info import run_command




def send_notification(request: NotificationRequest) -> None:
    # Try notify-send first (standard CLI notification helper)
    args = ["notify-send", request.title, request.message]
    if request.app_name:
        args.extend(["-a", request.app_name])
    if request.urgency:
        args.extend(["-u", request.urgency])

    stdout, stderr, returncode = run_command(args)
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


    # All attempts failed — raise to allow caller to handle reporting
    raise RuntimeError(f"Failed to send notification: {stderr or 'unknown error'}")


def clear_notifications() -> None:
    run_command(["dunstctl", "close-all"])


def parse_dunst_history(raw_history: str) -> List[NotificationRecord]:
    notifications: List[NotificationRecord] = []
    for line in raw_history.splitlines():
        line = line.strip()
        if not line:
            continue

        match = re.match(
            r'^\[?(?P<id>\d+)]?\s+(?P<app>\S+)\s+"(?P<title>[^"]+)"\s+"(?P<message>[^"]+)"',
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


def list_system_notifications() -> List[NotificationRecord]:
    stdout, stderr, returncode = run_command(["dunstctl", "history"])
    if returncode != 0 or not stdout:
        return list(notifications)
    return parse_dunst_history(stdout)
