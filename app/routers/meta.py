from typing import Optional

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user
from app.domain.meta import ToolCountResponse, ToolListResponse
from app.services.capabilities import get_available_tool_names

router = APIRouter(prefix="/meta", tags=["meta"])

@router.get("/tools/count", response_model=ToolCountResponse)
async def count_tools(
    _user: str = Depends(get_current_user),
) -> ToolCountResponse:
    """Count how many assistant tools are available on this host."""
    tools = get_available_tool_names()
    return ToolCountResponse(count=len(tools))


@router.get("/tools", response_model=ToolListResponse)
async def list_tools(
    filter: Optional[str] = None,
    _user: str = Depends(get_current_user),
) -> ToolListResponse:
    """List all assistant tool names available on this host, optionally filtered."""
    tools = get_available_tool_names()
    if filter:
        filter_lower = filter.lower()
        tools = {t for t in tools if filter_lower in t.lower()}
    return ToolListResponse(tools=sorted(list(tools)))
