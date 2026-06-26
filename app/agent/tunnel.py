import asyncio
import json
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests
import websockets
from dotenv import set_key

from app.utils.config import Config
config = Config()

_local_token: str | None = None
_local_token_expires = datetime.min.replace(tzinfo=timezone.utc)


async def tunnel(token):
    # Lazy imports to break circular dependency with app.agent.helpers
    from app.agent.helpers import agent_settings, websocket_tunnel_url, async_get_local_auth_token

    vps_url, agent_id, _ = agent_settings()
    uri = websocket_tunnel_url(vps_url, agent_id, token)
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
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=config.relay_read_timeout)
                except asyncio.TimeoutError:
                    print(f"No message from relay in {config.relay_read_timeout}s — assuming connection is dead")
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

                    local_url = f"{config.local_service_url}{path}"
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

                    request_kwargs = {"headers": headers, "timeout": config.local_service_timeout}
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

                    if resp.status_code == 401 and not config.local_service_auth_token:
                        print("Local request returned 401, refreshing local auth token and retrying")
                        global _local_token
                        _local_token = None
                        config.local_service_auth_token = None
                        config.local_service_auth_token_expires = None

                        # Clear from .env too
                        try:
                            set_key(config.dotenv_path, "LOCAL_SERVICE_AUTH_TOKEN", "")
                            set_key(config.dotenv_path, "LOCAL_SERVICE_AUTH_TOKEN_EXPIRES", "")
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
                    print(f"Local request timed out after {config.local_service_timeout}s: {local_url}")
                    await websocket.send(json.dumps({
                        "type": "forward_response",
                        "status_code": 504,
                        "body": f"Local service did not respond within {config.local_service_timeout}s",
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