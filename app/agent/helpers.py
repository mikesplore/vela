import asyncio
import getpass
import os
import socket
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse, urlunparse

from dotenv import set_key
import requests
import json

from app.agent.tunnel import tunnel

from app.utils.config import Config
config = Config()

_local_token: str | None = None
_local_token_expires = datetime.min.replace(tzinfo=timezone.utc)


def parse_metadata() -> dict | None:
    """Parse METADATA environment variable as JSON."""
    if not config.metadata_raw:
        return None
    try:
        return json.loads(config.metadata_raw)
    except json.JSONDecodeError:
        print(f"Warning: METADATA is not valid JSON, ignoring: {config.metadata_raw}")
        return None


def agent_settings() -> tuple[str, str, str]:
    return (
        _normalise_vps_url(_require_env("VPS_URL")),
        config.agent_id,
        config.agent_secret,
    )


def parse_local_expiry(expires_at: str) -> datetime:
    dt = datetime.fromisoformat(expires_at)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def get_local_auth_token(retries: int = 3, delay: float = 2.0) -> str:
    global _local_token, _local_token_expires

    now = datetime.now(timezone.utc)

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
        raise RuntimeError(
            "config.local_service_username and config.local_service_password must be set to obtain a local auth token"
        )

    token_url = f"{config.local_service_url}{config.local_service_token_path}"

    last_exc = None
    for attempt in range(retries):
        print(f"Obtaining local auth token from {token_url} (attempt {attempt + 1}/{retries})")
        resp = None
        try:
            resp = requests.post(
                token_url,
                json={"username": config.local_service_username, "password": config.local_service_password},
                timeout=config.local_service_timeout,
            )
            print(f"Local auth response status: {resp.status_code}")
            resp.raise_for_status()

            data = resp.json()
            _local_token = data.get("access_token")
            expiry_str = data.get("expires_at")
            _local_token_expires = parse_local_expiry(expiry_str)

            # Persist to .env
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
            print(f"Local auth token request failed (attempt {attempt + 1}/{retries}): {exc}")
            if resp is not None:
                print(f"Local auth failure response: status={resp.status_code}")
            if attempt < retries - 1:
                time.sleep(delay * (2 ** attempt))  # Exponential backoff

    raise last_exc


async def async_get_local_auth_token(retries: int = 3) -> str:
    return await asyncio.to_thread(get_local_auth_token, retries=retries)


async def wait_for_local_service(timeout: int = 60):
    """Wait for the local FastAPI service to be ready."""
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


def register():
    vps_url = _normalise_vps_url(_require_env("VPS_URL"))
    agent_id = config.agent_id

    # Construct the URL for this specific agent
    url = f"{vps_url.rstrip('/')}/register"

    # Build the registration payload matching the new VPS API
    payload = {
        "agent_id": agent_id,
    }

    regenerate = os.getenv("REGENERATE_SECRET", "").lower() in ("1", "true", "yes")

    if config.agent_secret and regenerate:
        # Password change: re-register with a new secret
        payload["regenerate_secret"] = "true"
        print(f"Re-registering agent '{agent_id}' to regenerate secret")
    elif not config.agent_secret:
        # First-time registration: include public_address and metadata
        if config.public_address:
            payload["public_address"] = config.public_address
        metadata = parse_metadata()
        if metadata:
            payload["metadata"] = metadata
        print(f"First-time registration of agent '{agent_id}'")
    else:
        # Normal re-registration: just get a fresh ws_token
        print(f"Re-registering agent '{agent_id}' for a fresh connection token")

    print(f"Registration payload: {payload}")

    # Only send X-API-Key header if we have a secret (for authenticated re-registration)
    headers = {}
    if config.agent_secret:
        headers["X-API-Key"] = config.agent_secret

    resp = requests.post(
        url,
        json=payload,
        headers=headers,
        timeout=config.local_service_timeout,
    )

    print(f"VPS register status: {resp.status_code}")

    if resp.status_code == 200:
        data = resp.json()

        # If the server returned a new secret, persist it to .env
        new_secret = data.get("secret")
        if new_secret:
            try:
                set_key(config.dotenv_path, "AGENT_SECRET", new_secret)
                print(f"Persisted new AGENT_SECRET to {config.dotenv_path}")
            except Exception as env_exc:
                print(f"Failed to persist AGENT_SECRET to .env: {env_exc}")

        return data.get("ws_token")

    raise Exception(f"Registration failed: {resp.text}")



async def start_agent_loop() -> None:
    await wait_for_local_service()

    backoff = 5
    max_backoff = 60

    while True:
        try:
            token = await asyncio.to_thread(register)
            print(f"Registered. Token: {token[:10]}...")
            await tunnel(token)
            # Tunnel exited cleanly — reset backoff
            backoff = 5
        except Exception as exc:
            print(f"Agent loop error: {exc}. Reconnecting in {backoff}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} must be set by setup before starting vela-agent")
    return value


def _default_agent_id() -> str:
    user = getpass.getuser() or "user"
    host = socket.gethostname() or "host"
    return f"{user}-{host}"


def _normalise_vps_url(raw_url: str) -> str:
    parsed = urlparse(raw_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("VPS_URL must include http:// or https:// and a host")
    return raw_url.rstrip("/")


def websocket_tunnel_url(vps_url: str, agent_id: str, token: str) -> str:
    parsed = urlparse(vps_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    query = urlencode({"agent_id": agent_id, "token": token})
    return urlunparse((scheme, parsed.netloc, "/tunnel", "", query, ""))