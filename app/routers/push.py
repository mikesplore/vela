from typing import Any

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user
from app.domain.push import PushDeviceRegistration, PushDeviceRemoval
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
