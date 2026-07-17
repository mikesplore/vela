"""Local API JWT acquisition and caching."""

from __future__ import annotations

import asyncio
import os
import secrets
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
import requests
import yaml
from dotenv import set_key

from app.utils.config import get_config

_local_token: str | None = None
_local_token_expires = datetime.min.replace(tzinfo=timezone.utc)
_local_auth_block_until = datetime.min.replace(tzinfo=timezone.utc)


def clear_local_auth_cache() -> None:
    """Drop in-memory local JWT so setup cannot reuse a stale token."""
    global _local_token, _local_token_expires, _local_auth_block_until
    _local_token = None
    _local_token_expires = datetime.min.replace(tzinfo=timezone.utc)
    _local_auth_block_until = datetime.min.replace(tzinfo=timezone.utc)


def _candidate_config_paths() -> list[Path]:
    override = os.getenv("REMOTEAGENT_CONFIG_PATH", "").strip()
    if override:
        return [Path(override)]
    return [
        Path.cwd() / "config.yaml",
        Path.home() / ".config" / "vela" / "config.yaml",
        Path(__file__).resolve().parent.parent / "config.yaml",
    ]


def _auto_create_local_auth_account() -> bool:
    """Create local API account credentials when none are saved yet."""
    config = get_config()
    cfg_path = next((p for p in _candidate_config_paths() if p.exists()), None)
    if not cfg_path:
        print("Cannot auto-create local auth account: config.yaml not found")
        return False

    try:
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        print(f"Cannot auto-create local auth account: failed to read config.yaml: {exc}")
        return False

    username = (os.getenv("USER", "") or "vela-agent").strip() or "vela-agent"
    password = secrets.token_urlsafe(18)
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    data["username"] = username
    data["password_hash"] = password_hash

    try:
        cfg_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    except Exception as exc:
        print(f"Cannot auto-create local auth account: failed to write config.yaml: {exc}")
        return False

    try:
        set_key(config.dotenv_path, "USERNAME", username)
        set_key(config.dotenv_path, "PASSWORD", password)
        set_key(config.dotenv_path, "LOCAL_SERVICE_USERNAME", username)
        set_key(config.dotenv_path, "LOCAL_SERVICE_PASSWORD", password)
    except Exception as exc:
        print(f"Auto-created account but failed to persist .env credentials: {exc}")

    config.username = username
    config.password_hash = password_hash
    config.local_service_username = username
    config.local_service_password = password

    try:
        subprocess.run(["systemctl", "--user", "restart", "vela.service"], check=False)
        time.sleep(1.5)
    except Exception as exc:
        print(f"Auto-created account; could not restart vela.service automatically: {exc}")

    print("Auto-created local auth account and refreshed service.")
    return True


def parse_local_expiry(expires_at: str) -> datetime:
    dt = datetime.fromisoformat(expires_at)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def get_local_auth_token(retries: int = 3, delay: float = 2.0) -> str:
    global _local_token, _local_token_expires, _local_auth_block_until

    config = get_config()
    now = datetime.now(timezone.utc)

    if now < _local_auth_block_until:
        wait_seconds = int((_local_auth_block_until - now).total_seconds())
        raise RuntimeError(
            f"Local auth temporarily blocked for {wait_seconds}s after recent auth failures"
        )

    # 1. Try in-memory token
    if _local_token and now + timedelta(seconds=30) < _local_token_expires:
        return _local_token

    # 2. Try environment/dotenv token
    if config.local_service_auth_token and config.local_service_auth_token_expires:
        try:
            expires = parse_local_expiry(config.local_service_auth_token_expires)
            if now + timedelta(seconds=30) < expires:
                _local_token = config.local_service_auth_token
                _local_token_expires = expires
                return _local_token
        except Exception as e:
            print(f"Error parsing config.local_service_auth_token_expires: {e}")

    # 3. Fallback for manually set token without expiry (if any)
    if config.local_service_auth_token and not config.local_service_auth_token_expires:
         return config.local_service_auth_token

    if not config.local_service_username or not config.local_service_password:
        created = _auto_create_local_auth_account()
        if not created:
            raise RuntimeError(
                "Local auth credentials are missing and automatic account creation failed"
            )

    token_url = f"{config.local_service_url}{config.local_service_token_path}"
    credential_candidates: list[tuple[str, str, str]] = []
    seen = set()
    for username, password, label in [
        ((config.local_service_username or "").strip(), (config.local_service_password or "").strip(), "LOCAL_SERVICE_*"),
        ((os.getenv("USERNAME", "") or "").strip(), (os.getenv("PASSWORD", "") or "").strip(), "USERNAME/PASSWORD"),
    ]:
        key = (username, password)
        if username and password and key not in seen:
            credential_candidates.append((username, password, label))
            seen.add(key)

    last_exc = None
    for attempt in range(retries):
        print(f"Obtaining local auth token from {token_url} (attempt {attempt + 1}/{retries})")
        for username, password, label in credential_candidates:
            resp = None
            try:
                resp = requests.post(
                    token_url,
                    json={"username": username, "password": password},
                    timeout=config.local_service_timeout,
                )
                print(f"Local auth response status ({label}): {resp.status_code}")
                resp.raise_for_status()

                data = resp.json()
                _local_token = data.get("access_token")
                expiry_str = data.get("expires_at")
                _local_token_expires = parse_local_expiry(expiry_str)

                # If fallback credentials worked, sync them as primary local creds.
                if label != "LOCAL_SERVICE_*":
                    try:
                        set_key(config.dotenv_path, "LOCAL_SERVICE_USERNAME", username)
                        set_key(config.dotenv_path, "LOCAL_SERVICE_PASSWORD", password)
                    except Exception as env_exc:
                        print(f"Failed to persist recovered local credentials to .env: {env_exc}")
                    config.local_service_username = username
                    config.local_service_password = password

                # Persist token to .env
                try:
                    set_key(config.dotenv_path, "LOCAL_SERVICE_AUTH_TOKEN", _local_token)
                    set_key(config.dotenv_path, "LOCAL_SERVICE_AUTH_TOKEN_EXPIRES", expiry_str)
                    print(f"Persisted local auth token to {config.dotenv_path}")
                except Exception as env_exc:
                    print(f"Failed to persist token to .env: {env_exc}")

                print(f"Obtained local auth token expiring at {_local_token_expires.isoformat()}")
                return _local_token
            except Exception as exc:
                last_exc = exc
                print(f"Local auth token request failed ({label}, attempt {attempt + 1}/{retries}): {exc}")
                if resp is not None:
                    print(f"Local auth failure response ({label}): status={resp.status_code}")
                    if resp.status_code == 429:
                        retry_after = 60
                        try:
                            retry_after = max(5, int(resp.headers.get("Retry-After", "60")))
                        except Exception:
                            retry_after = 60
                        _local_auth_block_until = datetime.now(timezone.utc) + timedelta(seconds=retry_after)
                        raise RuntimeError(
                            f"Local auth rate-limited (429). Backing off for {retry_after}s."
                        )
                    # On 401, try next credential candidate before blocking.
                    if resp.status_code == 401:
                        continue
        # All credential candidates failed this round; block briefly to avoid hammering.
        _local_auth_block_until = datetime.now(timezone.utc) + timedelta(seconds=60)
        if attempt < retries - 1:
            time.sleep(delay * (2 ** attempt))  # Exponential backoff

    raise last_exc


async def async_get_local_auth_token(retries: int = 3) -> str:
    return await asyncio.to_thread(get_local_auth_token, retries=retries)


async def wait_for_local_service(timeout: int = 60):
    """Wait for the local FastAPI service to be ready."""
    config = get_config()
    start_time = asyncio.get_event_loop().time()
    health_url = f"{config.local_service_url}/health"
    print(f"Waiting for local service at {health_url}...")

    while asyncio.get_event_loop().time() - start_time < timeout:
        try:
            resp = await asyncio.to_thread(requests.get, health_url, timeout=2)
            if resp.status_code == 200:
                print("Local service is up and healthy.")
                return True
        except Exception:
            pass
        await asyncio.sleep(2)

    print(f"Warning: Local service at {config.local_service_url} not reached after {timeout}s")
    return False
