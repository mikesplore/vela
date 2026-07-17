import asyncio
import json
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests
import websockets

from app.services import relay_status
from app.utils.config import get_config

config = get_config()

_local_token: str | None = None
_local_token_expires = datetime.min.replace(tzinfo=timezone.utc)

HEARTBEAT_INTERVAL = 30  # seconds


async def tunnel(token):
    """Maintain WebSocket tunnel to relay server with heartbeat and request forwarding."""
    # Lazy imports to avoid circular imports with agent modules
    from app.agent.envutil import agent_settings, websocket_tunnel_url
    from app.agent.local_auth import async_get_local_auth_token

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
            relay_status.mark_connected()

            # Start heartbeat sender
            heartbeat_task = asyncio.create_task(_heartbeat_loop(websocket))

            while True:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=config.relay_read_timeout)
                    relay_status.mark_message_received()
                except asyncio.TimeoutError:
                    print(f"No message from relay in {config.relay_read_timeout}s — assuming connection is dead")
                    raise  # Bubble up to outer handler; triggers reconnect

                request_id = None  # Reset per message so error handler always has it
                try:
                    req_data = json.loads(message)
                    msg_type = req_data.get("type")

                    if msg_type == "heartbeat":
                        # Heartbeat received from relay (or echo of our own), ignore
                        continue

                    if msg_type != "forward_request":
                        print(f"Unexpected message type: {msg_type}")
                        continue

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

                    upstream_authorization = next(
                        (value for key, value in headers.items() if key.lower() == "authorization"),
                        None,
                    )
                    if upstream_authorization:
                        # Keep upstream auth available for debugging/auditing while ensuring
                        # local API auth always uses a local token issued by this host.
                        headers["X-Upstream-Authorization"] = upstream_authorization

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

                    if resp.status_code == 401:
                        print("Local request returned 401, refreshing local auth token and retrying once")
                        global _local_token
                        _local_token = None
                        config.local_service_auth_token = None
                        config.local_service_auth_token_expires = None

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

                # --- except blocks at same level as try ---
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
        relay_status.mark_disconnected(tunnel_exc)
        print(f"Tunnel connection error: {tunnel_exc}")
        raise
    else:
        relay_status.mark_disconnected("Tunnel closed")


async def _heartbeat_loop(websocket):
    """Send periodic heartbeats to keep connection alive."""
    try:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
                heartbeat_msg = json.dumps({"type": "heartbeat"})
                await websocket.send(heartbeat_msg)
            except Exception:
                break
    except Exception as e:
        print(f"Heartbeat loop error: {e}")
