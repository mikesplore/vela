"""Relay credential persistence and env reload."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import set_key

from app.agent.local_auth import clear_local_auth_cache
from app.utils.config import get_config


def reload_agent_env(dotenv_path: Path | None = None) -> None:
    """Reload .env into process env + live Config after setup rewrites credentials."""
    from dotenv import load_dotenv

    config = get_config()
    path = dotenv_path or config.dotenv_path
    load_dotenv(path, override=True)
    clear_local_auth_cache()

    config.vps_url = os.getenv("VPS_URL", "").strip()
    config.agent_id = os.getenv("AGENT_ID", "").strip()
    config.agent_secret = (
        os.getenv("AGENT_CREDENTIAL", "").strip() or os.getenv("AGENT_SECRET", "").strip()
    )
    config.relay_secret = (
        os.getenv("RELAY_SECRET", "").strip() or os.getenv("AGENT_SECRET", "").strip()
    )
    config.local_service_url = os.getenv("LOCAL_SERVICE_URL", config.local_service_url).strip()
    config.local_service_username = (
        os.getenv("LOCAL_SERVICE_USERNAME", "").strip()
        or os.getenv("USERNAME", "").strip()
        or config.local_service_username
    )
    config.local_service_password = (
        os.getenv("LOCAL_SERVICE_PASSWORD", "").strip()
        or os.getenv("PASSWORD", "").strip()
        or config.local_service_password
    )
    config.local_service_auth_token = os.getenv("LOCAL_SERVICE_AUTH_TOKEN") or None
    config.local_service_auth_token_expires = os.getenv("LOCAL_SERVICE_AUTH_TOKEN_EXPIRES") or None
    if config.local_service_auth_token == "":
        config.local_service_auth_token = None
    if config.local_service_auth_token_expires == "":
        config.local_service_auth_token_expires = None


def reset_agent_credential() -> None:
    """Clear persisted relay credentials to force re-pairing."""
    config = get_config()
    try:
        set_key(config.dotenv_path, "AGENT_ID", "")
        set_key(config.dotenv_path, "AGENT_SECRET", "")
        set_key(config.dotenv_path, "AGENT_CREDENTIAL", "")
        set_key(config.dotenv_path, "RELAY_SECRET", "")
    except Exception as env_exc:
        print(f"Failed to clear agent credential in .env: {env_exc}")
    config.agent_id = ""
    config.agent_secret = ""
    config.relay_secret = ""


def _persist_agent_credential(agent_id: str, credential: str, relay_secret: str | None = None) -> None:
    config = get_config()
    if not relay_secret:
        raise RuntimeError("register/activate response missing relay_secret")

    try:
        set_key(config.dotenv_path, "AGENT_ID", agent_id)
        # AGENT_SECRET is kept as a backwards-compatible alias for relay_secret.
        set_key(config.dotenv_path, "AGENT_SECRET", relay_secret)
        set_key(config.dotenv_path, "AGENT_CREDENTIAL", credential)
        set_key(config.dotenv_path, "RELAY_SECRET", relay_secret)

        vps_url = (config.vps_url or os.getenv("VPS_URL", "")).rstrip("/")
        if vps_url and agent_id:
            spotify_redirect = f"{vps_url}/relay/{agent_id}/callback"
            set_key(config.dotenv_path, "SPOTIFY_REDIRECT_URI", spotify_redirect)
            os.environ["SPOTIFY_REDIRECT_URI"] = spotify_redirect

        print(f"Persisted AGENT_ID, RELAY_SECRET, AGENT_CREDENTIAL, and SPOTIFY_REDIRECT_URI to {config.dotenv_path}")
    except Exception as env_exc:
        print(f"Failed to persist AGENT credential to .env: {env_exc}")

    config.agent_id = agent_id
    config.agent_secret = credential
    config.relay_secret = relay_secret
