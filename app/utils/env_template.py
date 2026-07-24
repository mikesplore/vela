"""Canonical .env keys for Vela agent + integrations."""

from __future__ import annotations

import os
import re
from pathlib import Path

# Ordered template: every key the live services expect, even when empty.
ENV_TEMPLATE: list[tuple[str, str]] = [
    ("USERNAME", ""),
    ("PASSWORD", ""),
    ("LOCAL_SERVICE_USERNAME", ""),
    ("LOCAL_SERVICE_PASSWORD", ""),
    ("LOCAL_SERVICE_URL", "http://127.0.0.1:8765"),
    ("LOCAL_SERVICE_TOKEN_PATH", "/auth/token"),
    ("LOCAL_SERVICE_AUTH_TOKEN", ""),
    ("LOCAL_SERVICE_AUTH_TOKEN_EXPIRES", ""),
    ("LOCAL_SERVICE_TIMEOUT", "300"),
    ("RELAY_READ_TIMEOUT", "300"),
    ("VPS_URL", ""),
    ("AGENT_NAME", ""),
    ("AGENT_ID", ""),
    ("AGENT_SECRET", ""),
    ("AGENT_CREDENTIAL", ""),
    ("RELAY_SECRET", ""),
    ("PUBLIC_ADDRESS", ""),
    ("METADATA", ""),
    ("ASSISTANT_ACTION_PIN", ""),
    ("FIREWORKS_API_KEY", ""),
    ("IPINFO_TOKEN", ""),
    ("VELA_ASSISTANT_ENABLE_THINKING", "false"),
    ("VELA_FIREWORKS_API_URL", "https://api.fireworks.ai/inference/v1"),
    ("VELA_FIREWORKS_MODEL", "accounts/fireworks/models/qwen3p7-plus"),
    ("RECIPIENT_EMAIL", ""),
    ("RESEND_API_KEY", ""),
    ("RESEND_FROM_EMAIL", ""),
    ("VELA_ALERT_TIMEZONE", "UTC"),
    ("VELA_DAILY_SUMMARY_TIME", "18:00"),
    ("VELA_CPU_ALERT_THRESHOLD", "85"),
    ("VELA_MEMORY_ALERT_THRESHOLD", "85"),
    ("VELA_DISK_ALERT_THRESHOLD", "80"),
    ("VELA_SPIKE_CHECK_INTERVAL_MINUTES", "5"),
    ("VELA_ALERT_COOLDOWN_MINUTES", "15"),
    ("VELA_FCM_SERVICE_ACCOUNT_PATH", ""),
    ("VELA_ALERTMANAGER_WEBHOOK_SECRET", ""),
    ("SPOTIFY_CLIENT_ID", ""),
    ("SPOTIFY_CLIENT_SECRET", ""),
    ("SPOTIFY_REDIRECT_URI", ""),
    ("VELA_NETWORK_PUBLIC_IP_CACHE_SECONDS", "120"),
    ("VELA_NETWORK_WIFI_LIST_CACHE_SECONDS", "45"),
    ("VELA_DESKTOP_ENV_CHECK_INTERVAL_SECONDS", "30"),
]

_ENV_LINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def parse_env_values(text: str) -> dict[str, str]:
    """Parse KEY=value lines; later duplicates win."""
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _ENV_LINE_RE.match(stripped)
        if match:
            values[match.group(1)] = match.group(2)
    return values


def render_env_file(values: dict[str, str] | None = None) -> str:
    merged = values or {}
    lines = [f"{key}={merged.get(key, default)}" for key, default in ENV_TEMPLATE]
    return "\n".join(lines) + "\n"


def sync_env_file(path: Path, *, defaults: dict[str, str] | None = None) -> list[str]:
    """Ensure path contains every template key. Returns keys that were added."""
    defaults = defaults or {}
    existing = parse_env_values(path.read_text(encoding="utf-8")) if path.exists() else {}
    merged = dict(defaults)
    merged.update(existing)
    added = [key for key, default in ENV_TEMPLATE if key not in existing]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_env_file(merged), encoding="utf-8")
    os.chmod(path, 0o600)
    return added
