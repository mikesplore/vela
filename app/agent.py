import asyncio
import getpass
import os
import socket
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse, urlunparse

from dotenv import load_dotenv, set_key
import requests
import websockets
import json

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "vela"
ENV_CANDIDATES = (
    Path.cwd() / ".env",
    DEFAULT_CONFIG_DIR / ".env",
    Path(__file__).resolve().parent / ".env",
)
for dotenv_path in ENV_CANDIDATES:
    load_dotenv(dotenv_path)

DOTENV_PATH = next((path for path in ENV_CANDIDATES if path.exists()), Path.cwd() / ".env")


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


def _websocket_tunnel_url(vps_url: str, agent_id: str, token: str) -> str:
    parsed = urlparse(vps_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    query = urlencode({"agent_id": agent_id, "token": token})
    return urlunparse((scheme, parsed.netloc, "/tunnel", "", query, ""))


VPS_URL = os.getenv("VPS_URL", "").strip()
AGENT_ID = os.getenv("AGENT_ID", "").strip() or _default_agent_id()
AGENT_SECRET = os.getenv("AGENT_SECRET", "").strip()
PUBLIC_ADDRESS = os.getenv("PUBLIC_ADDRESS", "").strip() or None
METADATA_RAW = os.getenv("METADATA", "").strip()
LOCAL_SERVICE_URL = os.getenv("LOCAL_SERVICE_URL", "http://127.0.0.1:8765")
LOCAL_SERVICE_USERNAME = os.getenv("LOCAL_SERVICE_USERNAME", os.getenv("USERNAME", ""))
LOCAL_SERVICE_PASSWORD = os.getenv("LOCAL_SERVICE_PASSWORD", os.getenv("PASSWORD", ""))
LOCAL_SERVICE_TOKEN_PATH = os.getenv("LOCAL_SERVICE_TOKEN_PATH", "/auth/token")
LOCAL_SERVICE_AUTH_TOKEN = os.getenv("LOCAL_SERVICE_AUTH_TOKEN")
LOCAL_SERVICE_AUTH_TOKEN_EXPIRES = os.getenv("LOCAL_SERVICE_AUTH_TOKEN_EXPIRES")
LOCAL_SERVICE_TIMEOUT = int(os.getenv("LOCAL_SERVICE_TIMEOUT", "10"))

# How long to wait for a message from the relay before assuming the connection is dead.
RELAY_READ_TIMEOUT = int(os.getenv("RELAY_READ_TIMEOUT", "60"))

_local_token: str | None = None
_local_token_expires = datetime.min.replace(tzinfo=timezone.utc)


def _parse_metadata() -> dict | None:
    """Parse METADATA environment variable as JSON."""
    if not METADATA_RAW:
        return None
    try:
        return json.loads(METADATA_RAW)
    except json.JSONDecodeError:
        print(f"Warning: METADATA is not valid JSON, ignoring: {METADATA_RAW}")
        return None


def _agent_settings() -> tuple[str, str, str]:
    return (
        _normalise_vps_url(_require_env("VPS_URL")),
        AGENT_ID,
        AGENT_SECRET,
    )


def _parse_local_expiry(expires_at: str) -> datetime:
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
    if LOCAL_SERVICE_AUTH_TOKEN and LOCAL_SERVICE_AUTH_TOKEN_EXPIRES:
        try:
            expires = _parse_local_expiry(LOCAL_SERVICE_AUTH_TOKEN_EXPIRES)
            if now + timedelta(seconds=30) < expires:
                _local_token = LOCAL_SERVICE_AUTH_TOKEN
                _local_token_expires = expires
                return _local_token
        except Exception as e:
            print(f"Error parsing LOCAL_SERVICE_AUTH_TOKEN_EXPIRES: {e}")

    # 3. Fallback for manually set token without expiry (if any)
    if LOCAL_SERVICE_AUTH_TOKEN and not LOCAL_SERVICE_AUTH_TOKEN_EXPIRES:
         return LOCAL_SERVICE_AUTH_TOKEN

    if not LOCAL_SERVICE_USERNAME or not LOCAL_SERVICE_PASSWORD:
        raise RuntimeError(
            "LOCAL_SERVICE_USERNAME and LOCAL_SERVICE_PASSWORD must be set to obtain a local auth token"
        )

    token_url = f"{LOCAL_SERVICE_URL}{LOCAL_SERVICE_TOKEN_PATH}"

    last_exc = None
    for attempt in range(retries):
        print(f"Obtaining local auth token from {token_url} (attempt {attempt + 1}/{retries})")
        resp = None
        try:
            resp = requests.post(
                token_url,
                json={"username": LOCAL_SERVICE_USERNAME, "password": LOCAL_SERVICE_PASSWORD},
                timeout=LOCAL_SERVICE_TIMEOUT,
            )
            print(f"Local auth response status: {resp.status_code}")
            resp.raise_for_status()

            data = resp.json()
            _local_token = data.get("access_token")
            expiry_str = data.get("expires_at")
            _local_token_expires = _parse_local_expiry(expiry_str)

            # Persist to .env
            try:
                set_key(DOTENV_PATH, "LOCAL_SERVICE_AUTH_TOKEN", _local_token)
                set_key(DOTENV_PATH, "LOCAL_SERVICE_AUTH_TOKEN_EXPIRES", expiry_str)
                print(f"Persisted local auth token to {DOTENV_PATH}")
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
    health_url = f"{LOCAL_SERVICE_URL}/health"
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

    print(f"Warning: Local service at {LOCAL_SERVICE_URL} not reached after {timeout}s")
    return False


def register():
    vps_url = _normalise_vps_url(_require_env("VPS_URL"))
    agent_id = AGENT_ID

    # Construct the URL for this specific agent
    url = f"{vps_url.rstrip('/')}/register"

    # Build the registration payload matching the new VPS API
    payload = {
        "agent_id": agent_id,
    }

    regenerate = os.getenv("REGENERATE_SECRET", "").lower() in ("1", "true", "yes")

    if AGENT_SECRET and regenerate:
        # Password change: re-register with a new secret
        payload["regenerate_secret"] = True
        print(f"Re-registering agent '{agent_id}' to regenerate secret")
    elif not AGENT_SECRET:
        # First-time registration: include public_address and metadata
        if PUBLIC_ADDRESS:
            payload["public_address"] = PUBLIC_ADDRESS
        metadata = _parse_metadata()
        if metadata:
            payload["metadata"] = metadata
        print(f"First-time registration of agent '{agent_id}'")
    else:
        # Normal re-registration: just get a fresh ws_token
        print(f"Re-registering agent '{agent_id}' for a fresh connection token")

    print(f"Registration payload: {payload}")

    # Only send X-API-Key header if we have a secret (for authenticated re-registration)
    headers = {}
    if AGENT_SECRET:
        headers["X-API-Key"] = AGENT_SECRET

    resp = requests.post(
        url,
        json=payload,
        headers=headers,
        timeout=LOCAL_SERVICE_TIMEOUT,
    )

    print(f"VPS register status: {resp.status_code}")

    if resp.status_code == 200:
        data = resp.json()

        # If the server returned a new secret, persist it to .env
        new_secret = data.get("secret")
        if new_secret:
            try:
                set_key(DOTENV_PATH, "AGENT_SECRET", new_secret)
                print(f"Persisted new AGENT_SECRET to {DOTENV_PATH}")
            except Exception as env_exc:
                print(f"Failed to persist AGENT_SECRET to .env: {env_exc}")

        return data.get("ws_token")

    raise Exception(f"Registration failed: {resp.text}")


async def tunnel(token):
    vps_url, agent_id, _ = _agent_settings()
    uri = _websocket_tunnel_url(vps_url, agent_id, token)
    print(f"Connecting to {uri}...")
    try:
        async with websockets.connect(
            uri,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=10,
        ) as websocket:
            print("Tunnel established. Waiting for requests...")

            while True:
                # --- FIX 4: read timeout so zombie connections don't hang forever ---
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=RELAY_READ_TIMEOUT)
                except asyncio.TimeoutError:
                    print(f"No message from relay in {RELAY_READ_TIMEOUT}s — assuming connection is dead")
                    raise  # Bubble up to outer handler; triggers reconnect

                request_id = None  # Reset per message so error handler always has it
                try:
                    req_data = json.loads(message)
                    request_id = req_data.get("request_id") or req_data.get("id")
                    method = req_data.get("method", "GET")
                    path = req_data.get("path", "/")
                    body = req_data.get("body", None)
                    headers = {k: v for k, v in (req_data.get("headers") or {}).items()}
                    query_params = req_data.get("query") or req_data.get("query_params")
                    if query_params:
                        if isinstance(query_params, dict):
                            query_string = urlencode(query_params, doseq=True)
                        else:
                            query_string = str(query_params).lstrip("?")
                    else:
                        query_string = ""

                    local_url = f"{LOCAL_SERVICE_URL}{path}"
                    if query_string and "?" not in local_url:
                        local_url = f"{local_url}?{query_string}"

                    if "authorization" not in {k.lower() for k in headers}:
                        try:
                            headers["Authorization"] = f"Bearer {await async_get_local_auth_token()}"
                        except Exception as auth_exc:
                            print(f"Local auth failed while processing request: {auth_exc}")
                            await websocket.send(json.dumps({
                                "type": "forward_response",
                                "status_code": 500,
                                "body": f"Local auth failed: {auth_exc}",
                                "request_id": request_id,
                            }))
                            continue

                    request_kwargs = {"headers": headers, "timeout": LOCAL_SERVICE_TIMEOUT}
                    if body is not None:
                        if isinstance(body, str):
                            content_type = headers.get("content-type", "")
                            if content_type.startswith("application/json"):
                                try:
                                    body = json.loads(body)
                                except json.JSONDecodeError:
                                    pass
                        if isinstance(body, (dict, list)):
                            request_kwargs["json"] = body
                        else:
                            request_kwargs["data"] = body

                    resp = await asyncio.to_thread(
                        requests.request,
                        method,
                        local_url,
                        **request_kwargs,
                    )

                    # --- FIX 2: use `global` so the token is actually cleared ---
                    if resp.status_code == 401 and not os.getenv("LOCAL_SERVICE_AUTH_TOKEN"):
                        print("Local request returned 401, refreshing local auth token and retrying")
                        global _local_token, LOCAL_SERVICE_AUTH_TOKEN, LOCAL_SERVICE_AUTH_TOKEN_EXPIRES
                        _local_token = None
                        LOCAL_SERVICE_AUTH_TOKEN = None
                        LOCAL_SERVICE_AUTH_TOKEN_EXPIRES = None
                        
                        # Clear from .env too
                        try:
                            set_key(DOTENV_PATH, "LOCAL_SERVICE_AUTH_TOKEN", "")
                            set_key(DOTENV_PATH, "LOCAL_SERVICE_AUTH_TOKEN_EXPIRES", "")
                        except Exception:
                            pass

                        headers["Authorization"] = f"Bearer {await async_get_local_auth_token()}"
                        resp = await asyncio.to_thread(
                            requests.request,
                            method,
                            local_url,
                            **request_kwargs,
                        )

                    response_payload = {
                        "type": "forward_response",
                        "request_id": request_id,
                        "status_code": resp.status_code,
                        "headers": dict(resp.headers),
                        "body": resp.text,
                    }
                    print(f"Sending response payload for request_id={request_id}, status_code={resp.status_code}")
                    await websocket.send(json.dumps(response_payload))

                # --- FIX 1: except blocks are now correctly at the same level as try ---
                except requests.exceptions.Timeout:
                    print(f"Local request timed out after {LOCAL_SERVICE_TIMEOUT}s: {local_url}")
                    await websocket.send(json.dumps({
                        "type": "forward_response",
                        "status_code": 504,
                        "body": f"Local service did not respond within {LOCAL_SERVICE_TIMEOUT}s",
                        "request_id": request_id,
                    }))
                except requests.exceptions.ConnectionError as e:
                    print(f"Connection error to local service: {e}")
                    # If we can't connect, maybe the service is down or there's a network issue.
                    # We should probably notify the relay.
                    await websocket.send(json.dumps({
                        "type": "forward_response",
                        "status_code": 502,
                        "body": f"Bad Gateway: Could not connect to local service: {e}",
                        "request_id": request_id,
                    }))
                except Exception as e:
                    print(f"Error processing request: {e}")
                    try:
                        await websocket.send(json.dumps({
                            "type": "forward_response",
                            "status_code": 500,
                            "body": str(e),
                            "request_id": request_id,
                        }))
                    except Exception:
                        pass

    except Exception as tunnel_exc:
        print(f"Tunnel connection error: {tunnel_exc}")
        raise


async def start_agent_loop() -> None:
    await wait_for_local_service()

    # --- FIX 3: exponential backoff with a cap on reconnect attempts ---
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


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Vela Agent — connects to VPS relay")
    parser.add_argument(
        "--regenerate-secret",
        action="store_true",
        help="Re-register with the VPS to obtain a new agent secret (password change). "
             "Requires AGENT_SECRET to be set in the environment.",
    )
    args = parser.parse_args()

    if args.regenerate_secret:
        os.environ["REGENERATE_SECRET"] = "true"

    asyncio.run(start_agent_loop())


if __name__ == "__main__":
    main()
