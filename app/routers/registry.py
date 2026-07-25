"""Lazy router loading gated by runtime module capabilities."""
from __future__ import annotations

import importlib
import logging
from typing import Iterable

from fastapi import APIRouter

logger = logging.getLogger(__name__)

# Always registered — small routers used for discovery/admin regardless of host.
ALWAYS_ROUTERS: tuple[tuple[str, str], ...] = (
    ("app.routers.capabilities", "router"),
    ("app.routers.admin", "router"),
)

# Module key → (import path, router attribute). Spotify exposes two routers.
MODULE_ROUTERS: dict[str, tuple[tuple[str, str], ...]] = {
    "alerts": (("app.routers.alerts", "router"),),
    "display": (("app.routers.display", "router"),),
    "audio": (("app.routers.audio", "router"),),
    "clipboard": (("app.routers.clipboard", "router"),),
    "filesystem": (("app.routers.filesystem", "router"),),
    "input_control": (("app.routers.input_control", "router"),),
    "maintenance": (("app.routers.maintenance", "router"),),
    "docker": (("app.routers.docker", "router"),),
    "media": (("app.routers.media", "router"),),
    "monitoring": (("app.routers.monitoring", "router"),),
    "network": (("app.routers.network", "router"),),
    "notifications": (("app.routers.notifications", "router"),),
    "power": (("app.routers.power", "router"),),
    "processes": (("app.routers.processes", "router"),),
    "scheduler": (("app.routers.scheduler", "router"),),
    "security": (("app.routers.security", "router"),),
    "system_info": (("app.routers.system_info", "router"),),
    "assistant": (("app.routers.assistant", "router"),),
    "spotify": (
        ("app.routers.spotify", "spotify_router"),
        ("app.routers.spotify", "spotify_callback_alias_router"),
    ),
    "push": (("app.routers.push", "router"),),
}


def _import_router(module_path: str, attr: str) -> APIRouter:
    module = importlib.import_module(module_path)
    return getattr(module, attr)


def load_routers(enabled_modules: Iterable[str]) -> list[APIRouter]:
    """Import and return routers for modules available on this host."""
    enabled = set(enabled_modules)
    routers: list[APIRouter] = []

    for module_path, attr in ALWAYS_ROUTERS:
        routers.append(_import_router(module_path, attr))

    loaded_modules: list[str] = []
    skipped_modules: list[str] = []
    for module_key, entries in MODULE_ROUTERS.items():
        if module_key in enabled:
            for module_path, attr in entries:
                routers.append(_import_router(module_path, attr))
            loaded_modules.append(module_key)
        else:
            skipped_modules.append(module_key)

    logger.info(
        "Capability-gated routers: loaded %d modules (%s), skipped %d (%s)",
        len(loaded_modules),
        ", ".join(sorted(loaded_modules)) or "(none)",
        len(skipped_modules),
        ", ".join(sorted(skipped_modules)) or "(none)",
    )
    return routers
