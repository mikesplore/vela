from typing import Optional, List

from pydantic import BaseModel, Field


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

notifications: List[NotificationRecord] = []
next_notification_id = 1

