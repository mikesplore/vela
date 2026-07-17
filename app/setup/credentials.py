"""Credential wipe helpers for fresh setup.

Two auth layers:
- Local auth: Vela API server <-> agent tunnel (USERNAME/PASSWORD + JWT cache)
- Relay auth: agent <-> VPS (AGENT_ID, RELAY_SECRET, AGENT_CREDENTIAL)
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import set_key, unset_key


RELAY_CREDENTIAL_KEYS = (
    "AGENT_ID",
    "AGENT_SECRET",
    "AGENT_CREDENTIAL",
    "RELAY_SECRET",
)

LOCAL_AUTH_CACHE_KEYS = (
    "LOCAL_SERVICE_AUTH_TOKEN",
    "LOCAL_SERVICE_AUTH_TOKEN_EXPIRES",
)


def wipe_setup_credentials(dotenv_path: Path) -> None:
    """Clear relay + local-token cache from .env and process environment.

    Setup always starts fresh: old relay secrets and cached JWTs must not survive.
    Username/password for local API are rewritten by setup itself.
    """
    keys = (*RELAY_CREDENTIAL_KEYS, *LOCAL_AUTH_CACHE_KEYS)
    for key in keys:
        os.environ.pop(key, None)
        if not dotenv_path.exists():
            continue
        try:
            set_key(dotenv_path, key, "")
        except Exception:
            try:
                unset_key(dotenv_path, key)
            except Exception:
                pass

    try:
        from app.agent.local_auth import clear_local_auth_cache
        from app.utils.config import get_config

        clear_local_auth_cache()
        cfg = get_config()
        cfg.agent_id = ""
        cfg.agent_secret = ""
        cfg.relay_secret = ""
        cfg.local_service_auth_token = None
        cfg.local_service_auth_token_expires = None
    except Exception:
        pass

    print("Cleared previous relay credentials and local auth token cache.")
