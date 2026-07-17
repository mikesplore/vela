"""Shared agent environment / URL helpers."""

from __future__ import annotations

import json
import os
from urllib.parse import urlencode, urlparse, urlunparse

from app.utils.config import get_config


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} must be set by setup before starting vela-agent")
    return value


def _normalise_vps_url(raw_url: str) -> str:
    parsed = urlparse(raw_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("VPS_URL must include http:// or https:// and a host")
    return raw_url.rstrip("/")


def websocket_tunnel_url(vps_url: str, agent_id: str, token: str) -> str:
    parsed = urlparse(vps_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    query = urlencode({"agent_id": agent_id, "token": token})
    return urlunparse((scheme, parsed.netloc, "/tunnel", "", query, ""))


def agent_settings() -> tuple[str, str, str]:
    config = get_config()
    return (
        _normalise_vps_url(_require_env("VPS_URL")),
        config.agent_id,
        config.agent_secret,
    )


def parse_metadata() -> dict | None:
    """Parse METADATA environment variable as JSON."""
    config = get_config()
    if not config.metadata_raw:
        return None
    try:
        return json.loads(config.metadata_raw)
    except json.JSONDecodeError:
        print(f"Warning: METADATA is not valid JSON, ignoring: {config.metadata_raw}")
        return None
