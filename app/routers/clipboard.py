from typing import Any, Dict

import pyperclip
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import get_current_user

router = APIRouter(prefix="/clipboard", tags=["clipboard"])


class ClipboardData(BaseModel):
    text: str


class ClipboardWriteRequest(BaseModel):
    text: str


class StatusResponse(BaseModel):
    success: bool
    message: str


def _read_clipboard() -> str:
    try:
        return pyperclip.paste()
    except pyperclip.PyperclipException as exc:
        raise HTTPException(status_code=500, detail=str(exc))


def _write_clipboard(text: str) -> None:
    try:
        pyperclip.copy(text)
    except pyperclip.PyperclipException as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/readd", response_model=ClipboardData, dependencies=[Depends(get_current_user)])
async def read_clipboard() -> Any:
    """Read the current clipboard contents."""
    return ClipboardData(text=_read_clipboard())


@router.post("/write", response_model=StatusResponse, dependencies=[Depends(get_current_user)])
async def write_clipboard(request: ClipboardWriteRequest) -> Any:
    """Write text to the clipboard."""
    _write_clipboard(request.text)
    return StatusResponse(success=True, message="clipboard updated")


@router.post("/clear", response_model=StatusResponse, dependencies=[Depends(get_current_user)])
async def clear_clipboard() -> Any:
    """Clear the clipboard contents."""
    _write_clipboard("")
    return StatusResponse(success=True, message="clipboard cleared")
