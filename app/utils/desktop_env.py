"""Keep GUI session variables fresh for systemd-managed Vela.

GNOME/Mutter rotates ``.mutter-Xwaylandauth.*`` every login. A static
``~/.config/vela/desktop.env`` snapshot goes stale and X11 clients fail with
"Authorization required, but no authorization protocol specified".
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_desktop_env_last_check: float = 0.0

DESKTOP_ENV_KEYS = (
    "DISPLAY",
    "WAYLAND_DISPLAY",
    "XAUTHORITY",
    "DBUS_SESSION_BUS_ADDRESS",
    "XDG_RUNTIME_DIR",
    "XDG_SESSION_TYPE",
    "XDG_CURRENT_DESKTOP",
    "DESKTOP_SESSION",
)

DESKTOP_ENV_FILE = Path.home() / ".config" / "vela" / "desktop.env"


def _parse_systemctl_environment() -> dict[str, str]:
    try:
        proc = subprocess.run(
            ["systemctl", "--user", "show-environment"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return {}
    if proc.returncode != 0:
        return {}

    env: dict[str, str] = {}
    for line in (proc.stdout or "").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key] = value
    return env


def _newest_mutter_xauthority(runtime_dir: str) -> str | None:
    runtime = Path(runtime_dir)
    if not runtime.is_dir():
        return None
    candidates = sorted(
        runtime.glob(".mutter-Xwaylandauth.*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def _xauthority_usable(path: str | None) -> bool:
    return bool(path) and Path(path).is_file()


def refresh_desktop_env(*, force: bool = False, persist: bool = True) -> dict[str, str]:
    """Refresh process env from the live user session when X11 auth is stale."""
    current_xauth = os.environ.get("XAUTHORITY", "")
    if not force and _xauthority_usable(current_xauth):
        return {key: os.environ.get(key, "") for key in DESKTOP_ENV_KEYS}

    session_env = _parse_systemctl_environment()
    updated: dict[str, str] = {}

    for key in DESKTOP_ENV_KEYS:
        value = (session_env.get(key) or os.environ.get(key) or "").strip()
        if value:
            updated[key] = value

    runtime_dir = updated.get("XDG_RUNTIME_DIR") or os.environ.get("XDG_RUNTIME_DIR", "")
    xauth = updated.get("XAUTHORITY", "")
    if not _xauthority_usable(xauth) and runtime_dir:
        newest = _newest_mutter_xauthority(runtime_dir)
        if newest:
            updated["XAUTHORITY"] = newest

    if not updated.get("DISPLAY"):
        updated["DISPLAY"] = ":0"

    for key, value in updated.items():
        os.environ[key] = value

    if persist and updated:
        try:
            DESKTOP_ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
            DESKTOP_ENV_FILE.write_text(
                "\n".join(f"{key}={updated.get(key, '')}" for key in DESKTOP_ENV_KEYS) + "\n",
                encoding="utf-8",
            )
            os.chmod(DESKTOP_ENV_FILE, 0o600)
        except Exception as exc:
            logger.debug("Could not persist desktop.env: %s", exc)

    if updated.get("XAUTHORITY") and updated.get("XAUTHORITY") != current_xauth:
        logger.info("Refreshed desktop XAUTHORITY -> %s", updated["XAUTHORITY"])

    return updated


def ensure_desktop_env() -> None:
    """Ensure GUI env matches the live graphical session before X11/Wayland clients."""
    global _desktop_env_last_check

    current_xauth = os.environ.get("XAUTHORITY", "")
    if _xauthority_usable(current_xauth):
        return

    from app.utils.config import get_config

    interval = max(5, get_config().desktop_env_check_interval_seconds)
    now = time.monotonic()
    if now - _desktop_env_last_check < interval:
        return
    _desktop_env_last_check = now

    session_env = _parse_systemctl_environment()
    session_xauth = (session_env.get("XAUTHORITY") or "").strip()
    if session_xauth and session_xauth != current_xauth and _xauthority_usable(session_xauth):
        refresh_desktop_env(force=True, persist=True)
        return

    refresh_desktop_env(force=True, persist=True)
