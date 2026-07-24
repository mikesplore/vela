from fastapi import APIRouter, Depends

from app.dependencies import get_current_user
from app.domain.capabilities import CapabilitiesRefreshResponse, CapabilitiesResponse
from app.services import capabilities as capabilities_service

router = APIRouter(prefix="/capabilities", tags=["capabilities"])


@router.get("", response_model=CapabilitiesResponse)
async def list_capabilities(
    refresh: bool = False,
    _user: str = Depends(get_current_user),
) -> CapabilitiesResponse:
    """Return probed module and assistant-tool availability for this host."""
    return capabilities_service.get_capabilities(refresh=refresh)


@router.post("/refresh", response_model=CapabilitiesRefreshResponse)
async def refresh_capabilities(
    _user: str = Depends(get_current_user),
) -> CapabilitiesRefreshResponse:
    """Re-run capability probes and update the stored snapshot."""
    snapshot = capabilities_service.refresh_capabilities()
    return CapabilitiesRefreshResponse(
        checked_at=snapshot.checked_at,  # type: ignore[arg-type]
        modules_available=sum(1 for m in snapshot.modules.values() if m.available),
        tools_available=len(snapshot.assistant_tools.available),
    )
