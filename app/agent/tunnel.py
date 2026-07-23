import asyncio
import base64
import json
import logging
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
import websockets

from app.services import relay_status
from app.utils.config import get_config

config = get_config()
logger = logging.getLogger(__name__)

_local_token: str | None = None
_local_token_expires = datetime.min.replace(tzinfo=timezone.utc)

HEARTBEAT_INTERVAL = 30  # seconds
STREAM_PATH_SUFFIX = "/assistant/stream"
CHUNK_SIZE = 4096
# Responses larger than this are relayed in chunks instead of one JSON frame.
BUFFER_MAX_BYTES = 256 * 1024


def _is_streaming_request(path: str, method: str) -> bool:
    return method.upper() == "POST" and path.rstrip("/").endswith(STREAM_PATH_SUFFIX)


def _is_streaming_response(content_type: str | None) -> bool:
    if not content_type:
        return False
    return "text/event-stream" in content_type.lower()


def _content_length(response: httpx.Response) -> int | None:
    raw = response.headers.get("content-length")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _should_relay_streamed(expect_stream: bool, response: httpx.Response) -> bool:
    """Use chunked relay when the body may be large or size is unknown."""
    if expect_stream or _is_streaming_response(response.headers.get("content-type")):
        return True
    length = _content_length(response)
    if length is None:
        return True
    return length > BUFFER_MAX_BYTES


def _encode_ws_chunk(chunk: bytes) -> dict[str, str]:
    try:
        return {"body": chunk.decode("utf-8"), "body_encoding": "utf-8"}
    except UnicodeDecodeError:
        return {
            "body": base64.b64encode(chunk).decode("ascii"),
            "body_encoding": "base64",
        }


async def _send_forward_response(
        websocket,
        *,
        request_id: str | None,
        status_code: int,
        body: str,
        headers: dict | None = None,
) -> None:
    await websocket.send(json.dumps({
        "type": "forward_response",
        "request_id": request_id,
        "status_code": status_code,
        "headers": headers or {},
        "body": body,
    }))


async def _send_stream_start(
        websocket,
        *,
        request_id: str | None,
        status_code: int,
        headers: dict,
) -> None:
    await websocket.send(json.dumps({
        "type": "forward_response_start",
        "request_id": request_id,
        "status_code": status_code,
        "headers": headers,
    }))


async def _send_stream_chunk(websocket, *, request_id: str | None, chunk: bytes) -> None:
    await websocket.send(json.dumps({
        "type": "forward_response_chunk",
        "request_id": request_id,
        **_encode_ws_chunk(chunk),
    }))


async def _send_stream_end(websocket, *, request_id: str | None) -> None:
    await websocket.send(json.dumps({
        "type": "forward_response_end",
        "request_id": request_id,
    }))


def _local_timeout() -> httpx.Timeout:
    seconds = float(config.local_service_timeout)
    return httpx.Timeout(connect=30.0, read=seconds, write=seconds, pool=seconds)


def _local_client_limits() -> httpx.Limits:
    return httpx.Limits(max_connections=20, max_keepalive_connections=10)


def _prepare_body(body, headers: dict):
    if body is None:
        return None

    if isinstance(body, str):
        content_type = headers.get("content-type", "")
        if content_type.startswith("application/json"):
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                pass
        return body

    return body


def _build_request_kwargs(method: str, headers: dict, body) -> dict:
    request_kwargs: dict = {"headers": headers}
    prepared = _prepare_body(body, headers)
    if prepared is None:
        return request_kwargs
    if isinstance(prepared, (dict, list)):
        request_kwargs["json"] = prepared
    else:
        request_kwargs["content"] = prepared
    return request_kwargs


async def _relay_streaming_response(websocket, request_id: str | None, response: httpx.Response) -> None:
    await _send_stream_start(
        websocket,
        request_id=request_id,
        status_code=response.status_code,
        headers=dict(response.headers),
    )
    try:
        async for chunk in response.aiter_bytes(CHUNK_SIZE):
            if chunk:
                await _send_stream_chunk(websocket, request_id=request_id, chunk=chunk)
    finally:
        await _send_stream_end(websocket, request_id=request_id)


async def _relay_buffered_response(
        websocket,
        request_id: str | None,
        response: httpx.Response,
        content: bytes,
) -> None:
    body = content.decode("utf-8")
    logger.debug(
        "Relaying buffered response request_id=%s status=%s bytes=%d",
        request_id,
        response.status_code,
        len(content),
    )
    await _send_forward_response(
        websocket,
        request_id=request_id,
        status_code=response.status_code,
        headers=dict(response.headers),
        body=body,
    )


async def _relay_local_response(
        websocket,
        request_id: str | None,
        response: httpx.Response,
        *,
        expect_stream: bool,
) -> None:
    if _should_relay_streamed(expect_stream, response):
        await _relay_streaming_response(websocket, request_id, response)
        return

    content = await response.aread()
    await _relay_buffered_response(websocket, request_id, response, content)


async def _forward_local_request(
        websocket,
        *,
        request_id: str | None,
        method: str,
        local_url: str,
        headers: dict,
        body,
        expect_stream: bool,
        client: httpx.AsyncClient,
) -> None:
    request_kwargs = _build_request_kwargs(method, headers, body)

    async with client.stream(method, local_url, **request_kwargs) as response:
        if response.status_code == 401:
            global _local_token
            _local_token = None
            config.local_service_auth_token = None
            config.local_service_auth_token_expires = None

            from app.agent.local_auth import async_get_local_auth_token

            headers["Authorization"] = f"Bearer {await async_get_local_auth_token()}"
            request_kwargs = _build_request_kwargs(method, headers, body)
            await response.aclose()
            async with client.stream(method, local_url, **request_kwargs) as retry_response:
                await _relay_local_response(
                    websocket,
                    request_id,
                    retry_response,
                    expect_stream=expect_stream,
                )
            return

        await _relay_local_response(
            websocket,
            request_id,
            response,
            expect_stream=expect_stream,
        )


async def _handle_forward_request(
        websocket,
        req_data: dict,
        *,
        client: httpx.AsyncClient,
) -> None:
    from app.agent.local_auth import async_get_local_auth_token

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
        headers["X-Upstream-Authorization"] = upstream_authorization

    try:
        headers["Authorization"] = f"Bearer {await async_get_local_auth_token()}"
    except Exception as auth_exc:
        logger.warning("Local auth failed while processing request: %s", auth_exc)
        await _send_forward_response(
            websocket,
            request_id=request_id,
            status_code=500,
            body=f"Local auth failed: {auth_exc}",
        )
        return

    expect_stream = _is_streaming_request(path, method)
    try:
        await _forward_local_request(
            websocket,
            request_id=request_id,
            method=method,
            local_url=local_url,
            headers=headers,
            body=body,
            expect_stream=expect_stream,
            client=client,
        )
    except httpx.TimeoutException:
        logger.warning("Local request timed out after %ss: %s", config.local_service_timeout, local_url)
        await _send_forward_response(
            websocket,
            request_id=request_id,
            status_code=504,
            body=f"Local service did not respond within {config.local_service_timeout}s",
        )
    except httpx.ConnectError as exc:
        logger.warning("Connection error to local service: %s", exc)
        await _send_forward_response(
            websocket,
            request_id=request_id,
            status_code=502,
            body=f"Bad Gateway: Could not connect to local service: {exc}",
        )


async def tunnel(token):
    """Maintain WebSocket tunnel to relay server with heartbeat and request forwarding."""
    from app.agent.envutil import agent_settings, websocket_tunnel_url

    vps_url, agent_id, _ = agent_settings()
    uri = websocket_tunnel_url(vps_url, agent_id, token)
    print(f"Connecting to {uri}...")
    try:
        async with httpx.AsyncClient(
                timeout=_local_timeout(),
                limits=_local_client_limits(),
        ) as local_client, websockets.connect(
                uri,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=10,
        ) as websocket:
            print("Tunnel established. Waiting for requests...")
            relay_status.mark_connected()

            asyncio.create_task(_heartbeat_loop(websocket))

            while True:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=config.relay_read_timeout)
                    relay_status.mark_message_received()
                except asyncio.TimeoutError:
                    print(f"No message from relay in {config.relay_read_timeout}s — assuming connection is dead")
                    raise

                try:
                    req_data = json.loads(message)
                    msg_type = req_data.get("type")

                    if msg_type == "heartbeat":
                        continue

                    if msg_type != "forward_request":
                        print(f"Unexpected message type: {msg_type}")
                        continue

                    await _handle_forward_request(websocket, req_data, client=local_client)
                except Exception as exc:
                    logger.exception("Error processing relay request")
                    request_id = None
                    try:
                        req_data = json.loads(message)
                        request_id = req_data.get("request_id") or req_data.get("id")
                    except Exception:
                        pass
                    try:
                        await _send_forward_response(
                            websocket,
                            request_id=request_id,
                            status_code=500,
                            body=str(exc),
                        )
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
    except Exception as exc:
        print(f"Heartbeat loop error: {exc}")
