"""Host readiness checks that run before Vela writes service configuration."""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

MIN_FREE_BYTES = 512 * 1024 * 1024


def run_preflight(*, target_dir: Path, host: str, port: int, vps_url: str) -> list[dict[str, str]]:
    checks = [
        _check_writable_directory(target_dir),
        _check_disk_space(target_dir),
        _check_systemd_user(),
        _check_port(host, port),
        _check_vps_dns(vps_url),
        _check_desktop_session(),
    ]
    return checks


def has_failures(checks: list[dict[str, str]]) -> bool:
    return any(check["status"] == "failure" for check in checks)


def format_preflight(checks: list[dict[str, str]]) -> str:
    return "\n".join(f"[{check['status']}] {check['label']}: {check['detail']}" for check in checks)


def _check_writable_directory(target_dir: Path) -> dict[str, str]:
    try:
        with tempfile.NamedTemporaryFile(dir=target_dir, prefix=".vela-preflight-", delete=True):
            pass
    except OSError as exc:
        return _failure("Configuration storage", f"{target_dir} is not writable: {exc}")
    return _pass("Configuration storage", f"{target_dir} is writable.")


def _check_disk_space(target_dir: Path) -> dict[str, str]:
    free = shutil.disk_usage(target_dir).free
    if free < MIN_FREE_BYTES:
        return _failure("Disk space", f"Only {free // (1024 * 1024)} MiB free; at least 512 MiB is required.")
    return _pass("Disk space", f"{free // (1024 * 1024)} MiB free.")


def _check_systemd_user() -> dict[str, str]:
    try:
        result = subprocess.run(
            ["systemctl", "--user", "show-environment"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return _failure("User services", f"systemd user services are unavailable: {exc}")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "systemctl --user failed").strip()
        return _failure("User services", detail)
    return _pass("User services", "systemd user services are available.")


def _check_port(host: str, port: int) -> dict[str, str]:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind((host, port))
    except OSError as exc:
        return _warning("API port", f"{host}:{port} is already in use ({exc}). It may be an existing Vela service.")
    return _pass("API port", f"{host}:{port} is available.")


def _check_vps_dns(vps_url: str) -> dict[str, str]:
    host = urlparse(vps_url).hostname
    if not host:
        return _failure("VPS connectivity", "VPS URL does not contain a valid host.")
    try:
        socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        return _failure("VPS connectivity", f"Could not resolve {host}: {exc}")
    return _pass("VPS connectivity", f"{host} resolves. The relay health check runs next.")


def _check_desktop_session() -> dict[str, str]:
    if os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY"):
        return _pass("Desktop session", "Desktop session detected.")
    return _warning(
        "Desktop session",
        "No desktop session detected; display, input, notifications, and media controls may be unavailable.",
    )


def _pass(label: str, detail: str) -> dict[str, str]:
    return {"status": "pass", "label": label, "detail": detail}


def _warning(label: str, detail: str) -> dict[str, str]:
    return {"status": "warning", "label": label, "detail": detail}


def _failure(label: str, detail: str) -> dict[str, str]:
    return {"status": "failure", "label": label, "detail": detail}
