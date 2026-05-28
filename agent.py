import asyncio
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from dotenv import load_dotenv
import requests
import websockets
import json

load_dotenv()

VPS_URL = "https://vela.mikesplore.tech"
AGENT_ID = "my-laptop"
SECRET = "supersecret-agent-token"  # Replace with your actual secret
LOCAL_SERVICE_URL = os.getenv("LOCAL_SERVICE_URL", "http://localhost:8765")
LOCAL_SERVICE_USERNAME = os.getenv("LOCAL_SERVICE_USERNAME", os.getenv("USERNAME", "mike"))
LOCAL_SERVICE_PASSWORD = os.getenv("LOCAL_SERVICE_PASSWORD", os.getenv("PASSWORD", ""))
LOCAL_SERVICE_TOKEN_PATH = os.getenv("LOCAL_SERVICE_TOKEN_PATH", "/auth/token")
LOCAL_SERVICE_AUTH_TOKEN = os.getenv("LOCAL_SERVICE_AUTH_TOKEN")
LOCAL_SERVICE_TIMEOUT = int(os.getenv("LOCAL_SERVICE_TIMEOUT", "10"))

_local_token: str | None = None
_local_token_expires = datetime.min.replace(tzinfo=timezone.utc)

def _parse_local_expiry(expires_at: str) -> datetime:
    dt = datetime.fromisoformat(expires_at)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def get_local_auth_token() -> str:
    global _local_token, _local_token_expires

    if LOCAL_SERVICE_AUTH_TOKEN:
        return LOCAL_SERVICE_AUTH_TOKEN

    now = datetime.now(timezone.utc)
    if _local_token and now + timedelta(seconds=30) < _local_token_expires:
        return _local_token

    if not LOCAL_SERVICE_USERNAME or not LOCAL_SERVICE_PASSWORD:
        raise RuntimeError(
            "LOCAL_SERVICE_USERNAME and LOCAL_SERVICE_PASSWORD must be set to obtain a local auth token"
        )

    token_url = f"{LOCAL_SERVICE_URL}{LOCAL_SERVICE_TOKEN_PATH}"
    print(f"Obtaining local auth token from {token_url}")
    resp = None
    try:
        resp = requests.post(
            token_url,
            json={"username": LOCAL_SERVICE_USERNAME, "password": LOCAL_SERVICE_PASSWORD},
            timeout=LOCAL_SERVICE_TIMEOUT,
        )
        print(f"Local auth response status: {resp.status_code}")
        resp.raise_for_status()
    except Exception as exc:
        print(f"Local auth token request failed: {exc}")
        if resp is not None:
            print(f"Local auth failure response: status={resp.status_code}")
        raise

    data = resp.json()
    _local_token = data.get("access_token")
    _local_token_expires = _parse_local_expiry(data.get("expires_at"))
    print(f"Obtained local auth token expiring at {_local_token_expires.isoformat()}")
    return _local_token


async def async_get_local_auth_token() -> str:
    return await asyncio.to_thread(get_local_auth_token)


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
    async with websockets.connect(uri) as websocket:
        print("Tunnel established. Waiting for requests...")
        async for message in websocket:
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

                if resp.status_code == 401 and not LOCAL_SERVICE_AUTH_TOKEN:
                    print("Local request returned 401, refreshing local auth token and retrying")
                    _local_token = None
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
            except requests.exceptions.Timeout as exc:
                print(f"Local request timed out after {LOCAL_SERVICE_TIMEOUT}s: {local_url}")
                await websocket.send(json.dumps({
                    "type": "forward_response",
                    "status_code": 504,
                    "body": f"Local service did not respond within {LOCAL_SERVICE_TIMEOUT}s: {exc}",
                    "request_id": request_id,
                }))
            except Exception as e:
                print(f"Error processing request: {e}")
                await websocket.send(json.dumps({
                    "type": "forward_response",
                    "status_code": 500,
                    "body": str(e),
                    "request_id": request_id if 'request_id' in locals() else None,
                }))


async def start_agent_loop() -> None:
    while True:
        try:
            token = await asyncio.to_thread(register)
            print(f"Registered. Token: {token[:10]}...")
            await tunnel(token)
        except Exception as exc:
            print(f"Agent loop error: {exc}")
            await asyncio.sleep(5)


def main() -> None:
    asyncio.run(start_agent_loop())


if __name__ == "__main__":
    main()