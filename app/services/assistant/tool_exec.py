import asyncio
import base64
import json
import logging
from typing import Any
from urllib.parse import quote_plus

from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.domain.assistant import AssistantResponse
from app.services.assistant.tools import INPUT_CONFIRM_TOOLS, TOOL_ALIASES, TOOL_DEFINITIONS

logger = logging.getLogger("vela.assistant")


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

    if tool_name == "kill_process_by_name":
        name = tool_input.get("name")
        if not name:
            raise ValueError("tool_input.name is required for kill_process_by_name")
        path = path.format(name=quote_plus(str(name)))
        tool_input = {}

    # ── Defensive field normalisations (model hallucinations) ────────────────
    if tool_name == "set_volume":
        # Model sometimes sends "volume", "level", or "amount" instead of "value"
        if "value" not in tool_input:
            for alias in ("volume", "level", "amount", "percent"):
                if alias in tool_input:
                    tool_input = {"value": int(tool_input[alias])}
                    break

    headers: dict[str, str] = {}
    if tool_name != "upload_file":
        headers["Content-Type"] = "application/json"
    if confirmed and tool_name in INPUT_CONFIRM_TOOLS:
        headers["X-Confirm-Input"] = "true"
    if auth_header:
        headers["Authorization"] = auth_header

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        method = tool["method"].upper()
        if tool_name == "upload_file":
            file_base64 = tool_input.get("file_base64")
            path_value = tool_input.get("path")
            if not path_value or not file_base64:
                raise ValueError("tool_input.path and tool_input.file_base64 are required for upload_file")
            response = await client.post(
                path,
                data={"path": path_value},
                files={"file": ("upload.bin", base64.b64decode(file_base64), "application/octet-stream")},
                headers=headers,
                timeout=20.0,
            )
        elif method == "GET":
            response = await client.get(path, params=tool_input or {}, headers=headers, timeout=20.0)
        else:
            response = await client.request(method, path, json=tool_input or {}, headers=headers, timeout=20.0)

    if tool_name == "download_file":
        if response.status_code >= 400:
            try:
                error_data = response.json()
            except ValueError:
                error_data = response.text
            raise ValueError(f"Tool {tool_name} failed: {response.status_code} {error_data}")
        return {
            "path": tool_input.get("path"),
            "content_base64": base64.b64encode(response.content).decode("utf-8"),
            "content_type": response.headers.get("content-type", "application/octet-stream"),
        }

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


async def execute_tool_calls(request: Request, tool_calls: list[dict[str, object]], auth_header: str | None,
                              user_message: str = "", confirmed: bool = False) -> AssistantResponse:
    # Lazy import avoids circular dependency with helpers.compose_final_reply
    from app.services.assistant.helpers import compose_final_reply

    tasks = [
        execute_tool_safe(request.app, tc["tool"], tc.get("tool_input") or {}, auth_header, confirmed=confirmed)
        for tc in tool_calls
        if tc.get("tool") and tc["tool"] != "none"
    ]
    tool_results = list(await asyncio.gather(*tasks))

    if len(tool_results) == 1 and tool_results[0].get("tool") == "display_screenshot":
        result = tool_results[0].get("result") or {}
        image_base64 = result.get("image_base64") if isinstance(result, dict) else None
        if image_base64:
            return AssistantResponse(reply="Screenshot captured.", image_base64=image_base64)

    try:
        reply_text, art_url = await compose_final_reply(user_message, tool_results)
    except Exception as exc:
        logger.error("Final response composition failed: %s", exc, exc_info=True)
        reply_text = "\n".join(
            f"- **{r['tool']}**: {r['error'] or json.dumps(r['result'], separators=(',', ':'))}"
            for r in tool_results
        )
        art_url = None
    return AssistantResponse(reply=reply_text, art_url=art_url)
