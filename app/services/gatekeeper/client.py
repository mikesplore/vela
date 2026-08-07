"""HTTP client for the Gatekeeperd admin API (external to Vela)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.utils.config import get_config

logger = logging.getLogger(__name__)

_cached_token: str | None = None
_token_lock = asyncio.Lock()


def is_configured() -> bool:
    cfg = get_config()
    base = (cfg.gatekeeper_base_url or "").strip()
    if not base:
        return False
    if (cfg.gatekeeper_token or "").strip():
        return True
    email = (cfg.gatekeeper_email or "").strip()
    password = (cfg.gatekeeper_password or "").strip()
    return bool(email and password)


def base_url() -> str:
    return get_config().gatekeeper_base_url.strip().rstrip("/")


async def _fetch_token(client: httpx.AsyncClient) -> str:
    cfg = get_config()
    response = await client.post(
        f"{base_url()}/api/auth/login",
        json={"email": cfg.gatekeeper_email.strip(), "password": cfg.gatekeeper_password},
    )
    response.raise_for_status()
    data = response.json()
    token = data.get("token")
    if not token:
        raise ValueError("Gatekeeper login response missing token")
    return str(token)


async def auth_headers(client: httpx.AsyncClient, *, force_refresh: bool = False) -> dict[str, str]:
    global _cached_token
    cfg = get_config()
    static = (cfg.gatekeeper_token or "").strip()
    if static:
        return {"Authorization": f"Bearer {static}"}

    async with _token_lock:
        if force_refresh or not _cached_token:
            _cached_token = await _fetch_token(client)
        return {"Authorization": f"Bearer {_cached_token}"}


async def request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | list[tuple[str, str]] | None = None,
    json_body: dict[str, Any] | None = None,
) -> Any:
    if not is_configured():
        raise ValueError(
            "Gatekeeper is not configured. Set GATEKEEPER_BASE_URL and "
            "GATEKEEPER_TOKEN or GATEKEEPER_EMAIL + GATEKEEPER_PASSWORD in .env"
        )

    timeout = get_config().gatekeeper_timeout
    url = f"{base_url()}{path}"

    async with httpx.AsyncClient(timeout=timeout) as client:
        headers = await auth_headers(client)
        headers["Content-Type"] = "application/json"
        response = await client.request(method, url, params=params, json=json_body, headers=headers)

        if response.status_code == 401 and not (get_config().gatekeeper_token or "").strip():
            headers = await auth_headers(client, force_refresh=True)
            headers["Content-Type"] = "application/json"
            response = await client.request(method, url, params=params, json=json_body, headers=headers)

        try:
            data = response.json()
        except ValueError:
            raise ValueError(f"Gatekeeper returned non-JSON ({response.status_code}): {response.text[:500]}") from None

        if response.status_code >= 400:
            message = data.get("message") if isinstance(data, dict) else str(data)
            raise ValueError(f"Gatekeeper API error {response.status_code}: {message}")

        return data


def reset_token_cache() -> None:
    """Clear cached JWT (for tests)."""
    global _cached_token
    _cached_token = None
