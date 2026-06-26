"""Shared data models."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class PendingAction:
    action_id: str
    user_id: str
    session_id: str
    user_message: str
    tool_calls: list[dict[str, Any]]
    prompt: str
    requires_auth: bool
    created_at: datetime
    expires_at: datetime
    pin_attempts: int = 0