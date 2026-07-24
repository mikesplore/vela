from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ModuleCapability(BaseModel):
    available: bool
    config_enabled: bool = True
    reason: str | None = None
    missing_commands: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssistantToolsCapability(BaseModel):
    available: list[str] = Field(default_factory=list)
    unavailable: dict[str, str] = Field(default_factory=dict)


class CapabilitiesResponse(BaseModel):
    checked_at: datetime | None = None
    modules: dict[str, ModuleCapability] = Field(default_factory=dict)
    assistant_tools: AssistantToolsCapability = Field(default_factory=AssistantToolsCapability)


class CapabilitiesRefreshResponse(BaseModel):
    checked_at: datetime
    modules_available: int
    tools_available: int
