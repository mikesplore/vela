import time
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException
from app.dependencies import get_current_user
from domain.notifications import notifications
from domain.notifications import NotificationRecord, NotificationRequest, NotificationList
from app.services.notifications import send_notification as s_notification, list_system_notifications
from app.services.notifications import clear_notifications as c_notifications

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.post("/send", response_model=NotificationRecord, dependencies=[Depends(get_current_user)])
async def send_notification(request: NotificationRequest) -> Any:
    """Send a desktop notification and retain it in the agent history."""
    global next_notification_id
    try:
        s_notification(request)
    except Exception as exc:
        # Surface a clear error to the client when notifications can't be delivered
        raise HTTPException(status_code=500, detail=f"Notification failed: {exc}")
    record = NotificationRecord(
        id=next_notification_id,
        title=request.title,
        message=request.message,
        app_name=request.app_name,
        urgency=request.urgency,
        timestamp=time.time(),
    )
    notifications.append(record)
    next_notification_id += 1
    return record


@router.post("/clear", response_model=Dict[str, bool], dependencies=[Depends(get_current_user)])
async def clear_notifications() -> Any:
    """Clear agent-tracked notifications and attempt to close desktop notifications."""
    notifications.clear()
    c_notifications()
    return {"success": True}


@router.get("/read", response_model=NotificationList, dependencies=[Depends(get_current_user)])
async def read_notifications() -> Any:
    """Read notifications that were sent through this agent."""
    return NotificationList(notifications= notifications)


@router.get("/list", response_model=NotificationList, dependencies=[Depends(get_current_user)])
async def list_notifications() -> Any:
    """List desktop notification history or agent-tracked notifications."""
    return NotificationList(notifications=list_system_notifications())
