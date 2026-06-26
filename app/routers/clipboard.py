from typing import Any

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user
from app.domain.clipboard import ClipboardData, StatusResponse, ClipboardWriteRequest
from app.services.clipboard import read_clipboard as read, write_clipboard as write

router = APIRouter(prefix="/clipboard", tags=["clipboard"])


@router.get("/read", response_model=ClipboardData, dependencies=[Depends(get_current_user)])
async def read_clipboard() -> Any:
    """Read the current clipboard contents."""
    return ClipboardData(text=read())


@router.post("/write", response_model=StatusResponse, dependencies=[Depends(get_current_user)])
async def write_clipboard(request: ClipboardWriteRequest) -> Any:
    """Write text to the clipboard."""
    write(request.text)
    return StatusResponse(success=True, message="clipboard updated")


@router.post("/clear", response_model=StatusResponse, dependencies=[Depends(get_current_user)])
async def clear_clipboard() -> Any:
    """Clear the clipboard contents."""
    write("")
    return StatusResponse(success=True, message="clipboard cleared")
