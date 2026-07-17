from typing import Any
from datetime import UTC, datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse

from app.dependencies import get_current_user
from app.domain.admin import (
    AssistantAuditSummary,
    AdminSystemStatus,
    AuditEventsResponse,
    AuditSummary,
    ToolEventsResponse,
)
from app.services import audit as audit_service
from app.services import relay_status
from app.ui.admin_dashboard_page import render_admin_dashboard_page
from app.utils.config import get_config

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin_feature() -> None:
    flags = get_config().feature_flags or {}
    # Default on if unset so existing installs get the dashboard without re-setup.
    if flags.get("admin_dashboard", True) is False:
        raise HTTPException(status_code=404, detail="Admin dashboard is disabled")


@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard() -> HTMLResponse:
    """Browser UI for audit metrics. Auth is handled client-side via /auth/token."""
    _require_admin_feature()
    return HTMLResponse(content=render_admin_dashboard_page())


@router.get("/summary", response_model=AuditSummary, dependencies=[Depends(get_current_user)])
async def admin_summary(
    since_minutes: int = Query(60, ge=1, le=60 * 24 * 90),
    _user: str = Depends(get_current_user),
) -> Any:
    _require_admin_feature()
    return audit_service.summary(since_minutes=since_minutes)


@router.get("/status", response_model=AdminSystemStatus, dependencies=[Depends(get_current_user)])
async def admin_status(
    since_minutes: int = Query(60, ge=1, le=60 * 24 * 90),
    _user: str = Depends(get_current_user),
) -> Any:
    """Live local-backend status plus relay tunnel health and recent lifecycle events."""
    _require_admin_feature()
    return {
        "backend_status": "online",
        "server_time": datetime.now(UTC).isoformat(),
        "relay": relay_status.summary(since_minutes=since_minutes),
    }


@router.get("/events", response_model=AuditEventsResponse, dependencies=[Depends(get_current_user)])
async def admin_events(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    path_contains: str | None = Query(None),
    errors_only: bool = Query(False),
    since_minutes: int | None = Query(None, ge=1, le=60 * 24 * 90),
    _user: str = Depends(get_current_user),
) -> Any:
    _require_admin_feature()
    events = audit_service.list_events(
        limit=limit,
        offset=offset,
        path_contains=path_contains,
        status_min=400 if errors_only else None,
        since_minutes=since_minutes,
    )
    return AuditEventsResponse(events=events, total_stored=audit_service.count_events())


@router.get(
    "/assistant/summary",
    response_model=AssistantAuditSummary,
    dependencies=[Depends(get_current_user)],
)
async def admin_assistant_summary(
    since_minutes: int = Query(60, ge=1, le=60 * 24 * 90),
    _user: str = Depends(get_current_user),
) -> Any:
    _require_admin_feature()
    return audit_service.assistant_summary(since_minutes=since_minutes)


@router.get(
    "/assistant/events",
    response_model=ToolEventsResponse,
    dependencies=[Depends(get_current_user)],
)
async def admin_assistant_events(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    errors_only: bool = Query(False),
    since_minutes: int | None = Query(None, ge=1, le=60 * 24 * 90),
    _user: str = Depends(get_current_user),
) -> Any:
    _require_admin_feature()
    events = audit_service.list_tool_events(
        limit=limit,
        offset=offset,
        errors_only=errors_only,
        since_minutes=since_minutes,
    )
    return ToolEventsResponse(events=events, total_stored=audit_service.count_tool_events())


@router.post("/prune", dependencies=[Depends(get_current_user)])
async def admin_prune(_user: str = Depends(get_current_user)) -> Any:
    _require_admin_feature()
    audit_service.maybe_prune()
    return {"success": True, "total_stored": audit_service.count_events()}


@router.post("/clear", dependencies=[Depends(get_current_user)])
async def admin_clear_monitoring_history(
    confirmation: str = Body(..., embed=True),
    _user: str = Depends(get_current_user),
) -> Any:
    """Delete all persisted monitoring history after an explicit confirmation."""
    _require_admin_feature()
    if confirmation != "CLEAR":
        raise HTTPException(status_code=400, detail="Set confirmation to CLEAR to remove monitoring history")
    from app.db.audit_log import clear_monitoring_history

    return {"success": True, "deleted": clear_monitoring_history()}
