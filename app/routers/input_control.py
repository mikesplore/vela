from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from app.dependencies import get_current_user
from domain.audio import ActionResponse
from domain.input_control import MouseMoveRequest, MouseClickRequest, MouseDoubleClickRequest, MouseScrollRequest, \
    KeyboardTypeRequest, KeyboardKeyRequest
from utils.input_header import confirm_input_header
from utils.run_command import run_command

router = APIRouter(prefix="/input", tags=["input"])


@router.post("/mouse/move", response_model=ActionResponse,
             dependencies=[Depends(get_current_user), Depends(confirm_input_header)])
async def move_mouse(request: MouseMoveRequest) -> Any:
    """Move the mouse cursor to the given coordinates."""
    _, stderr, returncode = run_command(["xdotool", "mousemove", str(request.x), str(request.y)])
    if returncode != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or "Could not move mouse")
    return ActionResponse(success=True, message="Mouse moved.")


@router.post("/mouse/click", response_model=ActionResponse,
             dependencies=[Depends(get_current_user), Depends(confirm_input_header)])
async def click_mouse(request: MouseClickRequest) -> Any:
    """Click the mouse at the requested coordinates."""
    button_map = {"left": "1", "middle": "2", "right": "3"}
    _, stderr, returncode = run_command(
        ["xdotool", "mousemove", str(request.x), str(request.y), "click", button_map[request.button]]
    )
    if returncode != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or "Could not click mouse")
    return ActionResponse(success=True, message="Mouse clicked.")


@router.post("/mouse/double-click", response_model=ActionResponse,
             dependencies=[Depends(get_current_user), Depends(confirm_input_header)])
async def double_click_mouse(request: MouseDoubleClickRequest) -> Any:
    """Double click the mouse at the requested coordinates."""
    _, stderr, returncode = run_command(
        ["xdotool", "mousemove", str(request.x), str(request.y), "click", "1", "click", "1"]
    )
    if returncode != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=stderr or "Could not double-click mouse")
    return ActionResponse(success=True, message="Mouse double-clicked.")


@router.post("/mouse/scroll", response_model=ActionResponse,
             dependencies=[Depends(get_current_user), Depends(confirm_input_header)])
async def scroll_mouse(request: MouseScrollRequest) -> Any:
    """Scroll the mouse wheel up or down."""
    button = "4" if request.direction == "up" else "5"
    for _ in range(request.amount):
        _, stderr, returncode = run_command(["xdotool", "click", button])
        if returncode != 0:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail=stderr or "Could not scroll mouse")
    return ActionResponse(success=True, message="Mouse scrolled.")


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
