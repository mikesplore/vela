"""Runtime capability probes, persistence, and assistant tool filtering."""
from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.db import capabilities as capabilities_db
from app.domain.capabilities import (
    AssistantToolsCapability,
    CapabilitiesResponse,
    ModuleCapability,
)
from app.setup.deps import DEPENDENCY_GROUPS
from app.utils.config import get_config

logger = logging.getLogger(__name__)

# Setup dependency group label → config feature_flags key
DEP_GROUP_TO_FLAG: dict[str, str] = {
    "Filesystem": "filesystem",
    "Audio": "audio",
    "Display/Screenshot": "display",
    "Input Control": "input_control",
    "Media": "media",
    "Network": "network",
    "Notifications": "notifications",
    "Power": "power",
    "Security": "security",
    "System Info": "system_info",
    "Maintenance": "maintenance",
}

# Modules without CLI dependency groups — always probed separately
EXTRA_MODULES = ("monitoring", "processes", "scheduler", "docker", "alerts", "push", "spotify", "assistant")

# Map API path prefix → module key (for assistant tools)
PATH_PREFIX_TO_MODULE: list[tuple[str, str]] = [
    ("/system/", "system_info"),
    ("/network/", "network"),
    ("/monitor/", "monitoring"),
    ("/audio/", "audio"),
    ("/media/", "media"),
    ("/clipboard/", "clipboard"),
    ("/display/", "display"),
    ("/fs/", "filesystem"),
    ("/input/", "input_control"),
    ("/processes/", "processes"),
    ("/scheduler/", "scheduler"),
    ("/power/", "power"),
    ("/security/", "security"),
    ("/notifications/", "notifications"),
    ("/maintenance/", "maintenance"),
    ("/docker/", "docker"),
    ("/alerts/", "alerts"),
    ("/push/", "push"),
    ("/spotify/", "spotify"),
]

# Modules that need a graphical desktop session for most operations
DESKTOP_MODULES = frozenset({"display", "input_control", "notifications", "clipboard", "media"})

# Process tools that require a desktop session (others work headless)
PROCESS_DESKTOP_TOOLS = frozenset(
    {
        "open_application",
        "close_application",
        "active_window",
        "minimize_window",
        "close_window",
    }
)

# Network sub-features keyed by assistant tool name
NETWORK_WIFI_TOOLS = frozenset(
    {
        "get_wifi_status",
        "list_wifi_networks",
        "connect_wifi",
        "disconnect_wifi",
        "toggle_wifi",
    }
)
NETWORK_BLUETOOTH_TOOLS = frozenset(
    {
        "list_bluetooth_devices",
        "pair_bluetooth_device",
        "unpair_bluetooth_device",
        "toggle_bluetooth",
    }
)
NETWORK_VNSTAT_TOOLS = frozenset({"check_vnstat_status", "get_vnstat_data"})
NETWORK_SPEEDTEST_TOOLS = frozenset({"speed_test"})

# Filesystem tool that opens files in a GUI app
FILESYSTEM_DESKTOP_TOOLS = frozenset({"open_path"})

# In-memory cache populated by refresh_capabilities()
_cached_response: CapabilitiesResponse | None = None


def _flag_enabled(flag: str) -> bool:
    flags = get_config().feature_flags or {}
    return flags.get(flag, True) is not False


def _missing_commands(commands: list[str]) -> list[str]:
    return [cmd for cmd in commands if not shutil.which(cmd)]


def _clipboard_backends() -> list[str]:
    """Return installed pyperclip backends (any one is enough)."""
    backends: list[str] = []
    if shutil.which("wl-copy") and shutil.which("wl-paste"):
        backends.append("wl-clipboard")
    if shutil.which("xclip"):
        backends.append("xclip")
    if shutil.which("xsel"):
        backends.append("xsel")
    return backends


def _has_desktop_session() -> bool:
    wayland = os.environ.get("WAYLAND_DISPLAY", "").strip()
    if wayland:
        return True
    display = os.environ.get("DISPLAY", "").strip()
    if not display:
        return False
    if display.startswith(":"):
        try:
            display_num = display.split(".")[0].lstrip(":")
            return Path(f"/tmp/.X11-unix/X{display_num}").exists()
        except (ValueError, IndexError):
            return False
    return True


def _probe_dependency_modules() -> dict[str, ModuleCapability]:
    modules: dict[str, ModuleCapability] = {}
    for group in DEPENDENCY_GROUPS:
        flag = DEP_GROUP_TO_FLAG.get(group["feature"])
        if not flag:
            continue
        config_enabled = _flag_enabled(flag)
        missing = _missing_commands(group["commands"])
        available = config_enabled and not missing
        reason = None
        if not config_enabled:
            reason = "Disabled in config"
        elif missing:
            reason = f"Missing commands: {', '.join(missing)}"
        modules[flag] = ModuleCapability(
            available=available,
            config_enabled=config_enabled,
            reason=reason,
            missing_commands=missing,
        )
    return modules


def _probe_extra_modules(modules: dict[str, ModuleCapability]) -> None:
    config = get_config()

    # monitoring — psutil-based, always available when enabled
    monitoring_enabled = _flag_enabled("monitoring")
    modules["monitoring"] = ModuleCapability(
        available=monitoring_enabled,
        config_enabled=monitoring_enabled,
        reason=None if monitoring_enabled else "Disabled in config",
    )

    # processes — list/kill always work; desktop apps are tool-gated
    processes_enabled = _flag_enabled("processes")
    modules["processes"] = ModuleCapability(
        available=processes_enabled,
        config_enabled=processes_enabled,
        reason=None if processes_enabled else "Disabled in config",
    )

    # scheduler
    scheduler_enabled = _flag_enabled("scheduler")
    modules["scheduler"] = ModuleCapability(
        available=scheduler_enabled,
        config_enabled=scheduler_enabled,
        reason=None if scheduler_enabled else "Disabled in config",
    )

    # docker
    docker_enabled = _flag_enabled("docker") if "docker" in (config.feature_flags or {}) else True
    docker_installed = shutil.which("docker") is not None
    docker_running = False
    if docker_installed:
        try:
            from app.services.docker import get_docker_info

            info = get_docker_info()
            docker_running = info.running
        except Exception as exc:
            logger.debug("Docker probe failed: %s", exc)
    docker_available = docker_enabled and docker_installed and docker_running
    docker_reason = None
    if not docker_enabled:
        docker_reason = "Disabled in config"
    elif not docker_installed:
        docker_reason = "Docker CLI not installed"
    elif not docker_running:
        docker_reason = "Docker daemon is not running"
    modules["docker"] = ModuleCapability(
        available=docker_available,
        config_enabled=docker_enabled,
        reason=docker_reason,
        metadata={"installed": docker_installed, "running": docker_running},
    )

    # push
    push_enabled = _flag_enabled("push") if "push" in (config.feature_flags or {}) else True
    try:
        from app.services.push import get_configuration_error, is_configured as push_configured

        push_err = get_configuration_error()
        push_ok = push_configured()
    except Exception:
        push_err = "FCM service account not configured"
        push_ok = False
    modules["push"] = ModuleCapability(
        available=push_enabled and push_ok,
        config_enabled=push_enabled,
        reason=push_err if not push_ok else None,
        metadata={"configured": push_ok},
    )

    # alerts — email and/or push
    alerts_enabled = _flag_enabled("alerts") if "alerts" in (config.feature_flags or {}) else True
    try:
        from app.services import alert_delivery
        from app.services.push import is_configured as push_configured

        email_ok = alert_delivery.email_enabled()
        alerts_ok = email_ok or push_configured()
    except Exception:
        email_ok = False
        alerts_ok = False
    alerts_reason = None
    if not alerts_ok:
        alerts_reason = "Email (Resend) or push notifications not configured"
    modules["alerts"] = ModuleCapability(
        available=alerts_enabled and alerts_ok,
        config_enabled=alerts_enabled,
        reason=alerts_reason,
        metadata={"email_configured": email_ok},
    )

    # spotify
    spotify_enabled = _flag_enabled("spotify") if "spotify" in (config.feature_flags or {}) else True
    spotify_env_ok = bool(os.getenv("SPOTIFY_CLIENT_ID") and os.getenv("SPOTIFY_CLIENT_SECRET"))
    modules["spotify"] = ModuleCapability(
        available=spotify_enabled and spotify_env_ok,
        config_enabled=spotify_enabled,
        reason=None if spotify_env_ok else "Spotify credentials not configured in .env",
        metadata={"credentials_configured": spotify_env_ok},
    )

    # assistant — Fireworks API key
    assistant_enabled = True
    try:
        from app.services.assistant.helpers import get_api_key

        assistant_ok = bool(get_api_key())
    except Exception:
        assistant_ok = False
    modules["assistant"] = ModuleCapability(
        available=assistant_ok,
        config_enabled=assistant_enabled,
        reason=None if assistant_ok else "FIREWORKS_API_KEY not configured in .env",
    )

    # clipboard — pyperclip backend (X11 or Wayland)
    clipboard_enabled = _flag_enabled("clipboard")
    clipboard_backends = _clipboard_backends()
    clipboard_ok = bool(clipboard_backends)
    clipboard_reason = None
    if not clipboard_enabled:
        clipboard_reason = "Disabled in config"
    elif not clipboard_ok:
        clipboard_reason = "Missing clipboard backend (install xclip, xsel, or wl-clipboard)"
    modules["clipboard"] = ModuleCapability(
        available=clipboard_enabled and clipboard_ok,
        config_enabled=clipboard_enabled,
        reason=clipboard_reason,
        metadata={"backends": clipboard_backends},
    )

    # Apply desktop session constraints to GUI modules
    if not _has_desktop_session():
        for mod in DESKTOP_MODULES:
            if mod not in modules:
                continue
            entry = modules[mod]
            if entry.available:
                modules[mod] = ModuleCapability(
                    available=False,
                    config_enabled=entry.config_enabled,
                    reason="No desktop session (headless server)",
                    missing_commands=entry.missing_commands,
                    metadata=entry.metadata,
                )


def _network_subfeature_available(subfeature: str) -> tuple[bool, str | None]:
    if subfeature == "wifi":
        missing = _missing_commands(["nmcli"])
        if missing:
            return False, "nmcli not available (WiFi management unavailable)"
        return True, None
    if subfeature == "bluetooth":
        missing = _missing_commands(["bluetoothctl"])
        if missing:
            return False, "bluetoothctl not available"
        return True, None
    if subfeature == "vnstat":
        missing = _missing_commands(["vnstat"])
        if missing:
            return False, "vnstat not installed"
        return True, None
    if subfeature == "speedtest":
        try:
            import speedtest  # noqa: F401
        except ImportError:
            return False, "speedtest Python package not installed"
        return True, None
    return True, None


def _module_for_tool_path(path: str) -> str | None:
    for prefix, module in PATH_PREFIX_TO_MODULE:
        if path.startswith(prefix):
            return module
    return None


def _tool_availability(tool_name: str, tool_def: dict[str, Any], modules: dict[str, ModuleCapability]) -> tuple[bool, str | None]:
    path = tool_def.get("path", "")
    module_key = _module_for_tool_path(path)
    if not module_key:
        return True, None

    module = modules.get(module_key)
    if module and not module.available:
        return False, module.reason or f"{module_key} module unavailable"

    if module_key in DESKTOP_MODULES and not _has_desktop_session():
        return False, "No desktop session (headless server)"

    if tool_name in PROCESS_DESKTOP_TOOLS and not _has_desktop_session():
        return False, "No desktop session (headless server)"

    if tool_name in FILESYSTEM_DESKTOP_TOOLS and not _has_desktop_session():
        return False, "No desktop session (headless server)"

    if tool_name in NETWORK_WIFI_TOOLS:
        ok, reason = _network_subfeature_available("wifi")
        if not ok:
            return False, reason
    if tool_name in NETWORK_BLUETOOTH_TOOLS:
        ok, reason = _network_subfeature_available("bluetooth")
        if not ok:
            return False, reason
    if tool_name in NETWORK_VNSTAT_TOOLS:
        ok, reason = _network_subfeature_available("vnstat")
        if not ok:
            return False, reason
    if tool_name in NETWORK_SPEEDTEST_TOOLS:
        ok, reason = _network_subfeature_available("speedtest")
        if not ok:
            return False, reason

    return True, None


def _build_snapshot() -> CapabilitiesResponse:
    from app.services.assistant.tools import TOOL_DEFINITIONS

    modules = _probe_dependency_modules()
    _probe_extra_modules(modules)

    available_tools: list[str] = []
    unavailable_tools: dict[str, str] = {}
    db_rows: list[dict] = []

    for flag, mod in modules.items():
        db_rows.append(
            {
                "key": f"module:{flag}",
                "category": "module",
                "available": mod.available,
                "reason": mod.reason,
                "metadata": {
                    "config_enabled": mod.config_enabled,
                    "missing_commands": mod.missing_commands,
                    **mod.metadata,
                },
            }
        )

    for tool_name, tool_def in TOOL_DEFINITIONS.items():
        ok, reason = _tool_availability(tool_name, tool_def, modules)
        if ok:
            available_tools.append(tool_name)
        elif reason:
            unavailable_tools[tool_name] = reason
        db_rows.append(
            {
                "key": f"tool:{tool_name}",
                "category": "tool",
                "available": ok,
                "reason": reason,
                "metadata": {"path": tool_def.get("path"), "method": tool_def.get("method")},
            }
        )

    checked_at = capabilities_db.replace_capabilities(db_rows)
    return CapabilitiesResponse(
        checked_at=checked_at,
        modules=modules,
        assistant_tools=AssistantToolsCapability(
            available=sorted(available_tools),
            unavailable=unavailable_tools,
        ),
    )


def refresh_capabilities() -> CapabilitiesResponse:
    """Run all probes, persist to SQLite, and update the in-memory cache."""
    global _cached_response
    try:
        _cached_response = _build_snapshot()
        logger.info(
            "Capabilities refreshed: %d/%d modules available, %d/%d assistant tools available",
            sum(1 for m in _cached_response.modules.values() if m.available),
            len(_cached_response.modules),
            len(_cached_response.assistant_tools.available),
            len(_cached_response.assistant_tools.available) + len(_cached_response.assistant_tools.unavailable),
        )
    except Exception as exc:
        logger.warning("Capability refresh failed: %s", exc)
        if _cached_response is None:
            _cached_response = CapabilitiesResponse(checked_at=datetime.now(UTC))
    return _cached_response


def get_capabilities(*, refresh: bool = False) -> CapabilitiesResponse:
    """Return the cached capability snapshot, loading from DB or probing if needed."""
    global _cached_response
    if refresh:
        return refresh_capabilities()
    if _cached_response is not None:
        return _cached_response

    capabilities_db.init_capabilities_db()
    checked_at, rows = capabilities_db.load_capabilities()
    if rows:
        modules: dict[str, ModuleCapability] = {}
        available_tools: list[str] = []
        unavailable_tools: dict[str, str] = {}
        for row in rows:
            metadata = json.loads(row.metadata_json) if row.metadata_json else {}
            if row.category == "module":
                mod_key = row.key.removeprefix("module:")
                modules[mod_key] = ModuleCapability(
                    available=row.available,
                    config_enabled=metadata.get("config_enabled", True),
                    reason=row.reason,
                    missing_commands=metadata.get("missing_commands", []),
                    metadata={k: v for k, v in metadata.items() if k not in ("config_enabled", "missing_commands")},
                )
            elif row.category == "tool":
                tool_name = row.key.removeprefix("tool:")
                if row.available:
                    available_tools.append(tool_name)
                elif row.reason:
                    unavailable_tools[tool_name] = row.reason
        _cached_response = CapabilitiesResponse(
            checked_at=checked_at,
            modules=modules,
            assistant_tools=AssistantToolsCapability(
                available=sorted(available_tools),
                unavailable=unavailable_tools,
            ),
        )
        return _cached_response

    return refresh_capabilities()


def get_available_tool_names() -> set[str]:
    caps = get_capabilities()
    return set(caps.assistant_tools.available)


def is_module_available(module: str) -> bool:
    caps = get_capabilities()
    mod = caps.modules.get(module)
    return mod.available if mod else True


def is_tool_available(tool_name: str) -> bool:
    return tool_name in get_available_tool_names()
