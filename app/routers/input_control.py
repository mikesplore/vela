from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from app.dependencies import get_current_user
from app.domain.audio import ActionResponse
from app.domain.input_control import MouseMoveRequest, MouseClickRequest, MouseDoubleClickRequest, MouseScrollRequest, \
    KeyboardTypeRequest, KeyboardKeyRequest
from app.utils.input_header import confirm_input_header
from app.utils.run_command import run_command

router = APIRouter(prefix="/input", tags=["input"])


@router.post("/keyboard/type", response_model=ActionResponse,
             dependencies=[Depends(get_current_user), Depends(confirm_input_header)])
async def type_keyboard(request: KeyboardTypeRequest) -> Any:
    """Type text using the keyboard."""
    _, stderr, returncode = run_command(["xdotool", "type", "--delay", "0", request.text])
    if returncode != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or "Could not type text")
    return ActionResponse(success=True, message="Text typed.")


@router.post("/keyboard/key", response_model=ActionResponse,
             dependencies=[Depends(get_current_user), Depends(confirm_input_header)])
async def press_keyboard_keys(request: KeyboardKeyRequest) -> Any:
    """Press a keyboard key combination."""
    key_sequence = "+".join(request.keys)
    _, stderr, returncode = run_command(["xdotool", "key", key_sequence])
    if returncode != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or "Could not press keys")
    return ActionResponse(success=True, message="Keys pressed.")
