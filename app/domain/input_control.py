from typing import List, Optional
from pydantic import BaseModel, Field


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
