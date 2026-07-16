"""Write config.yaml and .env during setup."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

import bcrypt
import yaml


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
) -> Path:
    """Write a fresh .env. Relay credentials stay empty until pairing completes."""
    env_path = target_dir / ".env"
    lines = [
        f"USERNAME={username}",
        f"PASSWORD={password}",
        f"LOCAL_SERVICE_USERNAME={username}",
        f"LOCAL_SERVICE_PASSWORD={password}",
        f"LOCAL_SERVICE_URL=http://127.0.0.1:{server_port}",
        "LOCAL_SERVICE_TOKEN_PATH=/auth/token",
        "LOCAL_SERVICE_AUTH_TOKEN=",
        "LOCAL_SERVICE_AUTH_TOKEN_EXPIRES=",
        f"VPS_URL={vps_url}",
        f"AGENT_NAME={agent_label}",
        "AGENT_ID=",
        "AGENT_SECRET=",
        "AGENT_CREDENTIAL=",
        "RELAY_SECRET=",
        f"ASSISTANT_ACTION_PIN={assistant_pin}",
        "FIREWORKS_API_KEY=paste_your_key_here",
        "VELA_ASSISTANT_ENABLE_THINKING=false",
        "VELA_FIREWORKS_API_URL=https://api.fireworks.ai/inference/v1",
        "VELA_FIREWORKS_MODEL=accounts/fireworks/models/qwen3p7-plus",
        "RECIPIENT_EMAIL=your_personal_email",
        "RESEND_API_KEY=your_resend_api_key",
        "RESEND_FROM_EMAIL=your_resend_email",
        "SPOTIFY_CLIENT_ID=your_spotify_client_id_here",
        "SPOTIFY_CLIENT_SECRET=your_spotify_client_secret_here",
        f"SPOTIFY_REDIRECT_URI={vps_url}/relay/your_agent_id_after_pairing/callback",
    ]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(env_path, 0o600)
    return env_path
