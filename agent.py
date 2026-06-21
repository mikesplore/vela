import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from dotenv import load_dotenv, set_key
import requests
import websockets
import json

DOTENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(DOTENV_PATH)

VPS_URL = "https://vela.mikesplore.tech"
AGENT_ID = "my-laptop"
SECRET = "supersecret-agent-token"  # Replace with your actual secret
LOCAL_SERVICE_URL = os.getenv("LOCAL_SERVICE_URL", "http://127.0.0.1:8765")
LOCAL_SERVICE_USERNAME = os.getenv("LOCAL_SERVICE_USERNAME", os.getenv("USERNAME", "mike"))
LOCAL_SERVICE_PASSWORD = os.getenv("LOCAL_SERVICE_PASSWORD", os.getenv("PASSWORD", ""))
LOCAL_SERVICE_TOKEN_PATH = os.getenv("LOCAL_SERVICE_TOKEN_PATH", "/auth/token")
LOCAL_SERVICE_AUTH_TOKEN = os.getenv("LOCAL_SERVICE_AUTH_TOKEN")
LOCAL_SERVICE_AUTH_TOKEN_EXPIRES = os.getenv("LOCAL_SERVICE_AUTH_TOKEN_EXPIRES")
LOCAL_SERVICE_TIMEOUT = int(os.getenv("LOCAL_SERVICE_TIMEOUT", "10"))

# How long to wait for a message from the relay before assuming the connection is dead.
RELAY_READ_TIMEOUT = int(os.getenv("RELAY_READ_TIMEOUT", "60"))

_local_token: str | None = None
_local_token_expires = datetime.min.replace(tzinfo=timezone.utc)


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
    resp = requests.post(
        f"{VPS_URL}/register",
        json={"agent_id": AGENT_ID, "secret": SECRET},
    )
    print(f"VPS register status: {resp.status_code}")
    if resp.status_code == 200:
        return resp.json().get("ws_token")
    raise Exception(f"Registration failed: {resp.text}")


async def tunnel(token):
    uri = f"wss://{VPS_URL.replace('https://', '')}/tunnel?agent_id={AGENT_ID}&token={token}"
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
    asyncio.run(start_agent_loop())


if __name__ == "__main__":
    main()