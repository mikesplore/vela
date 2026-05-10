import subprocess
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from dependencies import get_current_user

router = APIRouter(prefix="/input", tags=["input"])


def _run_command(cmd: list[str], timeout: int = 10) -> tuple[str, str, int]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        return "", str(exc), 1


def confirm_input_header(x_confirm_input: Optional[str] = Header(None, alias="X-Confirm-Input")) -> bool:
    if not x_confirm_input or x_confirm_input.lower() != "true":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="X-Confirm-Input header is required and must be true",
        )
    return True


class MouseMoveRequest(BaseModel):
    x: int
    y: int


class MouseClickRequest(BaseModel):
    x: int
    y: int
    button: str = Field(..., pattern="^(left|right|middle)$")


class MouseDoubleClickRequest(BaseModel):
    x: int
    y: int


class MouseScrollRequest(BaseModel):
    direction: str = Field(..., pattern="^(up|down)$")
    amount: int = Field(..., ge=1)


class KeyboardTypeRequest(BaseModel):
    text: str


class KeyboardKeyRequest(BaseModel):
    keys: List[str] = Field(..., min_items=1)


class ActionResponse(BaseModel):
    success: bool
    message: Optional[str] = None


@router.post("/mouse/move", response_model=ActionResponse, dependencies=[Depends(get_current_user), Depends(confirm_input_header)])
async def move_mouse(request: MouseMoveRequest) -> Any:
    """Move the mouse cursor to the given coordinates."""
    _, stderr, returncode = _run_command(["xdotool", "mousemove", str(request.x), str(request.y)])
    if returncode != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or "Could not move mouse")
    return ActionResponse(success=True, message="Mouse moved.")


@router.post("/mouse/click", response_model=ActionResponse, dependencies=[Depends(get_current_user), Depends(confirm_input_header)])
async def click_mouse(request: MouseClickRequest) -> Any:
    """Click the mouse at the requested coordinates."""
    button_map = {"left": "1", "middle": "2", "right": "3"}
    _, stderr, returncode = _run_command(
        ["xdotool", "mousemove", str(request.x), str(request.y), "click", button_map[request.button]]
    )
    if returncode != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or "Could not click mouse")
    return ActionResponse(success=True, message="Mouse clicked.")


@router.post("/mouse/double-click", response_model=ActionResponse, dependencies=[Depends(get_current_user), Depends(confirm_input_header)])
async def double_click_mouse(request: MouseDoubleClickRequest) -> Any:
    """Double click the mouse at the requested coordinates."""
    _, stderr, returncode = _run_command(
        ["xdotool", "mousemove", str(request.x), str(request.y), "click", "1", "click", "1"]
    )
    if returncode != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or "Could not double-click mouse")
    return ActionResponse(success=True, message="Mouse double-clicked.")


@router.post("/mouse/scroll", response_model=ActionResponse, dependencies=[Depends(get_current_user), Depends(confirm_input_header)])
async def scroll_mouse(request: MouseScrollRequest) -> Any:
    """Scroll the mouse wheel up or down."""
    button = "4" if request.direction == "up" else "5"
    for _ in range(request.amount):
        _, stderr, returncode = _run_command(["xdotool", "click", button])
        if returncode != 0:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or "Could not scroll mouse")
    return ActionResponse(success=True, message="Mouse scrolled.")


@router.post("/keyboard/type", response_model=ActionResponse, dependencies=[Depends(get_current_user), Depends(confirm_input_header)])
async def type_keyboard(request: KeyboardTypeRequest) -> Any:
    """Type text using the keyboard."""
    _, stderr, returncode = _run_command(["xdotool", "type", "--delay", "0", request.text])
    if returncode != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or "Could not type text")
    return ActionResponse(success=True, message="Text typed.")


@router.post("/keyboard/key", response_model=ActionResponse, dependencies=[Depends(get_current_user), Depends(confirm_input_header)])
async def press_keyboard_keys(request: KeyboardKeyRequest) -> Any:
    """Press a keyboard key combination."""
    key_sequence = "+".join(request.keys)
    _, stderr, returncode = _run_command(["xdotool", "key", key_sequence])
    if returncode != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or "Could not press keys")
    return ActionResponse(success=True, message="Keys pressed.")
