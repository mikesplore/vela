"""Write config.yaml and .env during setup."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

import bcrypt
import yaml

from app.utils.env_template import ENV_TEMPLATE, render_env_file

# Optional integrations collected during setup. Empty means "leave unset".
OPTIONAL_ENV_FIELDS = (
    ("fireworks_api_key", "FIREWORKS_API_KEY", "Fireworks API key (assistant)"),
    ("ipinfo_token", "IPINFO_TOKEN", "IPinfo token (network location fallback)"),
    ("resend_api_key", "RESEND_API_KEY", "Resend API key (email alerts)"),
    ("resend_from_email", "RESEND_FROM_EMAIL", "Resend from email"),
    ("recipient_email", "RECIPIENT_EMAIL", "Alert recipient email"),
    ("spotify_client_id", "SPOTIFY_CLIENT_ID", "Spotify client ID"),
    ("spotify_client_secret", "SPOTIFY_CLIENT_SECRET", "Spotify client secret"),
)


def empty_optional_integrations() -> dict[str, str]:
    return {key: "" for key, _, _ in OPTIONAL_ENV_FIELDS}


def write_config_yaml(
    target_dir: Path,
    username: str,
    password: str,
    server_host: str,
    server_port: int,
    allowed_dirs: list[str],
    assistant_pin: str,
) -> Path:
    config_path = target_dir / "config.yaml"
    config = {
        "host": server_host,
        "port": server_port,
        "secret_key": secrets.token_urlsafe(32),
        "token_expire_minutes": 1440,
        "allowed_origins": [],
        "allowed_base_dirs": allowed_dirs,
        "rate_limit_default": "100/minute",
        "route_rate_limits": {"/auth/token": "10/minute", "/ping": "60/minute"},
        "feature_flags": {
            "display": True,
            "audio": True,
            "power": True,
            "notifications": True,
            "network": True,
            "filesystem": True,
            "input_control": True,
            "system_info": True,
            "monitoring": True,
            "processes": True,
            "security": True,
            "scheduler": True,
            "maintenance": True,
            "media": True,
            "clipboard": True,
            "admin_dashboard": True,
        },
        "username": username,
        "password_hash": bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
        "log_level": "INFO",
    }
    if assistant_pin:
        config["assistant_action_pin"] = assistant_pin
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return config_path


def write_env_file(
    target_dir: Path,
    username: str,
    password: str,
    vps_url: str,
    agent_label: str,
    server_port: int,
    assistant_pin: str,
    optional: dict[str, str] | None = None,
) -> Path:
    """Write a fresh .env. Relay credentials stay empty until pairing completes."""
    opts = empty_optional_integrations()
    if optional:
        for key in opts:
            opts[key] = (optional.get(key) or "").strip()

    env_path = target_dir / ".env"
    values = {key: default for key, default in ENV_TEMPLATE}
    values.update(
        {
            "USERNAME": username,
            "PASSWORD": password,
            "LOCAL_SERVICE_USERNAME": username,
            "LOCAL_SERVICE_PASSWORD": password,
            "LOCAL_SERVICE_URL": f"http://127.0.0.1:{server_port}",
            "VPS_URL": vps_url,
            "AGENT_NAME": agent_label,
            "ASSISTANT_ACTION_PIN": assistant_pin,
            "FIREWORKS_API_KEY": opts["fireworks_api_key"],
            "IPINFO_TOKEN": opts["ipinfo_token"],
            "RECIPIENT_EMAIL": opts["recipient_email"],
            "RESEND_API_KEY": opts["resend_api_key"],
            "RESEND_FROM_EMAIL": opts["resend_from_email"],
            "SPOTIFY_CLIENT_ID": opts["spotify_client_id"],
            "SPOTIFY_CLIENT_SECRET": opts["spotify_client_secret"],
        }
    )
    env_path.write_text(render_env_file(values), encoding="utf-8")
    os.chmod(env_path, 0o600)
    return env_path
