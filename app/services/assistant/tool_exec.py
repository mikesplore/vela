import asyncio
import base64
import json
import logging
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from fastapi import FastAPI, HTTPException, Request
from httpx import ASGITransport, AsyncClient

from app.domain.assistant import AssistantResponse
from app.services.assistant.tools import INPUT_CONFIRM_TOOLS, TOOL_ALIASES, TOOL_DEFINITIONS
from app.services.assistant.workflow import next_execution_stage, prepare_tool_calls
from app.services.filesystem import validate_path
from app.utils.config import get_config

logger = logging.getLogger("vela.assistant")

_BINARY_RESULT_KEYS = ("content_base64", "image_base64")
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico"}


def _format_bytes(num: int) -> str:
    value = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{num} B"


def _substitute_path_params(path: str, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    remaining = dict(payload)
    for key in re.findall(r"\{(\w+)\}", path):
        if key not in remaining:
            raise ValueError(f"tool_input.{key} is required")
        path = path.replace(f"{{{key}}}", quote_plus(str(remaining.pop(key))))
    return path, remaining


def _detect_image(path: Path, data: bytes) -> tuple[bool, str]:
    """Return (is_image, content_type) from extension and magic bytes."""
    ext = path.suffix.lower()
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return True, "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return True, "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return True, "image/gif"
    if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
        return True, "image/webp"
    if data.startswith(b"BM"):
        return True, "image/bmp"
    if data.startswith(b"\x00\x00\x01\x00"):
        return True, "image/x-icon"
    if ext in _IMAGE_EXTENSIONS:
        return True, {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
            ".ico": "image/x-icon",
        }.get(ext, "application/octet-stream")
    return False, "application/octet-stream"


def sanitize_tool_result_for_llm(result: Any) -> Any:
    """Strip binary payloads so they never enter an LLM prompt."""
    if not isinstance(result, dict):
        return result
    if not any(k in result for k in _BINARY_RESULT_KEYS):
        return result
    sanitized = {k: v for k, v in result.items() if k not in _BINARY_RESULT_KEYS}
    sanitized["content_omitted"] = True
    sanitized["content_omitted_reason"] = "binary content delivered to client only"
    return sanitized


def sanitize_tool_results_for_llm(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            **r,
            "result": sanitize_tool_result_for_llm(r.get("result")),
        }
        for r in results
    ]


def download_image_payload(tool_results: list[dict[str, Any]]) -> tuple[str, str] | None:
    """
    If results are a single successful image download, return (display_name, image_base64).
    Used for screenshot-style fast-path (no second LLM call).
    """
    if len(tool_results) != 1:
        return None
    entry = tool_results[0]
    if entry.get("tool") != "download_file" or entry.get("error"):
        return None
    result = entry.get("result") or {}
    if not isinstance(result, dict):
        return None
    image_b64 = result.get("image_base64")
    if not result.get("is_image") or not image_b64:
        return None
    path = result.get("path") or "image"
    return Path(str(path)).name, image_b64


async def _execute_download_file(
        app: FastAPI,
        tool_input: dict[str, Any],
        headers: dict[str, str],
) -> dict[str, Any]:
    path_value = tool_input.get("path")
    if not path_value:
        raise ValueError("tool_input.path is required for download_file")

    try:
        target = validate_path(str(path_value), must_exist=True)
    except HTTPException as exc:
        raise ValueError(exc.detail) from exc
    if target.is_dir():
        raise ValueError("Path must be a file")

    size = target.stat().st_size
    max_bytes = get_config().assistant_max_download_bytes
    if size > max_bytes:
        return {
            "path": str(target),
            "size_bytes": size,
            "max_bytes": max_bytes,
            "too_large": True,
            "message": (
                f"File is too large to transfer ({_format_bytes(size)}). "
                f"Maximum is {_format_bytes(max_bytes)}."
            ),
        }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/fs/download",
            params={"path": str(target)},
            headers=headers,
            timeout=20.0,
        )

    if response.status_code >= 400:
        try:
            error_data = response.json()
        except ValueError:
            error_data = response.text
        raise ValueError(f"Tool download_file failed: {response.status_code} {error_data}")

    data = response.content
    is_image, content_type = _detect_image(target, data)
    encoded = base64.b64encode(data).decode("utf-8")
    result: dict[str, Any] = {
        "path": str(target),
        "size_bytes": size,
        "content_type": content_type,
        "is_image": is_image,
    }
    if is_image:
        # Same field the client already uses for screenshots.
        result["image_base64"] = encoded
    else:
        result["content_base64"] = encoded
    return result


async def _execute_tool(
        app: FastAPI,
        tool_name: str,
        tool_input: dict[str, Any],
        auth_header: str | None,
        confirmed: bool = False,
) -> dict[str, Any]:
    resolved_tool = TOOL_ALIASES.get(tool_name, tool_name)
    if resolved_tool not in TOOL_DEFINITIONS:
        raise ValueError(f"Unknown tool: {tool_name}")
    tool_name = resolved_tool

    tool = TOOL_DEFINITIONS[tool_name]
    path = tool["path"]
    payload = dict(tool_input or {})

    if tool_name == "kill_process_by_name":
        name = payload.get("name")
        if not name:
            raise ValueError("tool_input.name is required for kill_process_by_name")
        path = path.format(name=quote_plus(str(name)))
        payload = {}

    path, payload = _substitute_path_params(path, payload)

    # ── Defensive field normalisations (model hallucinations) ────────────────
    if tool_name == "set_volume":
        # Model sometimes sends "volume", "level", or "amount" instead of "value"
        if "value" not in payload:
            for alias in ("volume", "level", "amount", "percent"):
                if alias in payload:
                    payload = {"value": int(payload[alias])}
                    break

    headers: dict[str, str] = {}
    if tool_name != "upload_file":
        headers["Content-Type"] = "application/json"
    if confirmed and tool_name in INPUT_CONFIRM_TOOLS:
        headers["X-Confirm-Input"] = "true"
    if auth_header:
        headers["Authorization"] = auth_header

    if tool_name == "download_file":
        return await _execute_download_file(app, payload, headers)

    method = tool["method"].upper()
    use_query = tool.get("query_input") or method == "GET"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        if tool_name == "upload_file":
            file_base64 = payload.get("file_base64")
            path_value = payload.get("path")
            if not path_value or not file_base64:
                raise ValueError("tool_input.path and tool_input.file_base64 are required for upload_file")
            response = await client.post(
                path,
                data={"path": path_value},
                files={"file": ("upload.bin", base64.b64decode(file_base64), "application/octet-stream")},
                headers=headers,
                timeout=20.0,
            )
        elif use_query:
            response = await client.request(method, path, params=payload or None, headers=headers, timeout=20.0)
        else:
            response = await client.request(method, path, json=payload or {}, headers=headers, timeout=20.0)

    try:
        data = response.json()
    except ValueError:
        raise ValueError(f"Tool {tool_name} returned invalid JSON: {response.text}")

    if response.status_code >= 400:
        raise ValueError(f"Tool {tool_name} failed: {response.status_code} {data}")
    return data


async def execute_tool_safe(
        app: FastAPI,
        tool_name: str,
        tool_input: dict[str, Any],
        auth_header: str | None,
        confirmed: bool = False,
) -> dict[str, Any]:
    """Wrapper that catches errors so one failing tool doesn't abort the others."""
    try:
        result = await _execute_tool(app, tool_name, tool_input, auth_header, confirmed=confirmed)
        return {"tool": tool_name, "result": result, "error": None}
    except Exception as exc:
        logger.error("Tool %s failed: %s", tool_name, exc, exc_info=True)
        return {"tool": tool_name, "result": {}, "error": str(exc)}


async def execute_tool_audited(
        app: FastAPI,
        tool_name: str,
        tool_input: dict[str, Any],
        auth_header: str | None,
        *,
        request_id: str | None = None,
        user_id: str | None = None,
        confirmed: bool = False,
) -> dict[str, Any]:
    """Execute a tool and persist only safe operational metadata."""
    started = time.monotonic()
    result = await execute_tool_safe(app, tool_name, tool_input, auth_header, confirmed=confirmed)
    duration_ms = (time.monotonic() - started) * 1000
    try:
        from app.db.audit_log import insert_tool_call_event

        insert_tool_call_event(
            request_id=request_id or "unknown",
            tool_name=str(result.get("tool") or tool_name),
            duration_ms=duration_ms,
            succeeded=not bool(result.get("error")),
            user_id=user_id,
            error=str(result["error"])[:1_000] if result.get("error") else None,
        )
    except Exception as exc:
        logger.debug("Tool audit write skipped: %s", exc)
    return result


async def execute_tool_plan(
        prepared_calls: list[dict[str, Any]],
        execute_call,
) -> list[dict[str, Any]]:
    """Run a dependency plan in parallel stages, preserving result order."""
    completed: dict[str, dict[str, Any]] = {}

    while len(completed) < len(prepared_calls):
        ready, skipped = next_execution_stage(prepared_calls, completed)
        for call, result in skipped:
            completed[call["id"]] = result
        if ready:
            results = await asyncio.gather(*(execute_call(call) for call in ready))
            for call, result in zip(ready, results):
                completed[call["id"]] = result

    return [completed[call["id"]] for call in prepared_calls]


async def execute_tool_results(
        request: Request,
        tool_calls: list[dict[str, object]],
        auth_header: str | None,
        confirmed: bool = False,
) -> list[dict[str, Any]]:
    prepared_calls = prepare_tool_calls(tool_calls)

    async def _execute_call(call: dict[str, Any]) -> dict[str, Any]:
        return await execute_tool_audited(
            request.app,
            call["tool"],
            call["tool_input"],
            auth_header,
            request_id=getattr(request.state, "request_id", None),
            user_id=getattr(request.state, "audit_user_id", None),
            confirmed=confirmed,
        )

    return await execute_tool_plan(prepared_calls, _execute_call)


async def response_from_tool_results(user_message: str, tool_results: list[dict[str, Any]]) -> AssistantResponse:
    # Lazy import avoids circular dependency with helpers.compose_final_reply
    from app.services.assistant.helpers import compose_final_reply

    if len(tool_results) == 1 and tool_results[0].get("tool") == "display_screenshot":
        result = tool_results[0].get("result") or {}
        image_base64 = result.get("image_base64") if isinstance(result, dict) else None
        if image_base64:
            return AssistantResponse(reply="Screenshot captured.", image_base64=image_base64)

    image_download = download_image_payload(tool_results)
    if image_download:
        name, image_base64 = image_download
        return AssistantResponse(reply=f"Here's {name}.", image_base64=image_base64)

    try:
        reply_text, art_url = await compose_final_reply(user_message, tool_results)
    except Exception as exc:
        logger.error("Final response composition failed: %s", exc, exc_info=True)
        safe = sanitize_tool_results_for_llm(tool_results)
        reply_text = "\n".join(
            f"- **{r['tool']}**: {r['error'] or json.dumps(r['result'], separators=(',', ':'))}"
            for r in safe
        )
        art_url = None
    return AssistantResponse(reply=reply_text, art_url=art_url)


async def execute_tool_calls(request: Request, tool_calls: list[dict[str, object]], auth_header: str | None,
                              user_message: str = "", confirmed: bool = False) -> AssistantResponse:
    tool_results = await execute_tool_results(request, tool_calls, auth_header, confirmed=confirmed)
    return await response_from_tool_results(user_message, tool_results)
