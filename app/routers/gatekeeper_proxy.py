from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.dependencies import get_current_user
from app.services.gatekeeper.client import is_configured as gatekeeper_is_configured

router = APIRouter(prefix="/api/admin", tags=["gatekeeper-proxy"])


def _require_gatekeeper_configured() -> None:
    if not gatekeeper_is_configured():
        # Mirror the behavior of "capability-gated" endpoints: if Gatekeeper isn't
        # configured on this host, the proxy shouldn't exist.
        raise HTTPException(status_code=404, detail="Gatekeeper is not configured")


@router.api_route("/{path:path}", methods=["GET", "POST", "PATCH", "PUT", "DELETE"])
async def gatekeeper_admin_proxy(
    request: Request,
    path: str,
    _user: str = Depends(get_current_user),
) -> Any:
    """
    Proxy Gatekeeperd admin endpoints through Vela.

    This exists so remote clients (including via the VPS relay) can reach Gatekeeperd's
    `/api/admin/*` API without Vela directly hosting those routes.
    """
    _require_gatekeeper_configured()

    from app.services.gatekeeper.client import request as gatekeeper_request

    method = request.method.upper()
    proxied_path = f"/api/admin/{path}".rstrip("/")
    if proxied_path != "/api/admin" and not proxied_path.startswith("/api/admin/"):
        raise HTTPException(status_code=400, detail="Invalid path")

    params = list(request.query_params.multi_items())

    json_body: dict[str, Any] | None = None
    if method not in {"GET", "HEAD"}:
        raw = await request.body()
        if raw:
            try:
                json_body = await request.json()
            except Exception as exc:  # pragma: no cover
                raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    try:
        return await gatekeeper_request(
            method,
            proxied_path,
            params=params or None,
            json_body=json_body,
        )
    except ValueError as exc:
        # Gatekeeper errors are "upstream" from Vela; treat as Bad Gateway.
        raise HTTPException(status_code=502, detail=str(exc)) from exc
