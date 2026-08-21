"""Small security helpers shared by HTTP endpoints."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from typing import Any

from fastapi import Header, HTTPException, status

from app.utils.config import get_config


def opaque_error_id() -> str:
    return uuid.uuid4().hex[:12]


def token_fingerprint(value: str | None) -> str:
    if not value:
        return "none"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def require_confirmed_action(
    x_confirm_action: str | None = Header(default=None, alias="X-Confirm-Action"),
    x_action_pin: str | None = Header(default=None, alias="X-Action-PIN"),
) -> bool:
    """Require explicit confirmation for direct high-impact control APIs.

    The confirmation header is intentionally separate from the input-control
    header. If an action PIN is configured, direct callers must also provide it.
    """
    if (x_confirm_action or "").strip().lower() != "true":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="X-Confirm-Action header is required and must be true",
        )
    configured_pin = (get_config().assistant_action_pin or "").strip()
    if configured_pin and not x_action_pin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="X-Action-PIN header is required")
    if configured_pin and not secrets.compare_digest(x_action_pin.strip(), configured_pin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid action PIN")
    return True


def redact_text(value: Any, *, limit: int = 500) -> str:
    """Return bounded text without common credential-bearing fields."""
    text = str(value)
    for marker in ("Authorization:", "Bearer ", "X-Secret:", "password=", "token="):
        if marker.lower() in text.lower():
            text = f"[redacted: {marker.strip(':= ')}]"
            break
    return text[:limit]
