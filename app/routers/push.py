from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_current_user
from app.domain.push import PushDeviceRegistration, PushDeviceRemoval, PushSendRequest, PushSendResponse
from app.services import push

router = APIRouter(prefix="/push", tags=["push"])


@router.post("/devices", dependencies=[Depends(get_current_user)])
async def register_push_device(
    body: PushDeviceRegistration,
    user: str = Depends(get_current_user),
) -> Any:
    """Register or refresh this Android installation's FCM token."""
    push.register_device(user_id=user, token=body.token, installation_id=body.installation_id)
    return {"success": True}


@router.delete("/devices", dependencies=[Depends(get_current_user)])
async def unregister_push_device(
    body: PushDeviceRemoval,
    user: str = Depends(get_current_user),
) -> Any:
    return {"success": push.unregister_device(user_id=user, token=body.token)}


@router.post("/send", response_model=PushSendResponse, dependencies=[Depends(get_current_user)])
async def send_push_notification(
    body: PushSendRequest,
    user: str = Depends(get_current_user),
) -> Any:
    """Send a push notification to the current user's registered devices."""
    if not push.is_configured():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Push notifications are not configured")
    delivered = push.send_push(title=body.title, body=body.body, data=body.data, user_id=user)
    return PushSendResponse(success=delivered > 0, delivered=delivered, configured=True)
