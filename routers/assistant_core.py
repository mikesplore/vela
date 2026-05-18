import asyncio
import base64
import json
import logging
import os
import re
from typing import Any
from urllib.parse import quote_plus

import dashscope
from dashscope import Generation
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from config import Config
from routers.assistant_tools import INPUT_CONFIRM_TOOLS, SYSTEM_TOOL_PROMPT, TOOL_DEFINITIONS

config = Config()
logger = logging.getLogger("vela.assistant")

# In-memory session store: {user_id: [{"role": "user|assistant", "content": "..."}, ...]}
SESSION_STORE: dict[str, list[dict[str, str]]] = {}
MAX_HISTORY_CHARS = 4000  # Token-budget-aware trimming instead of message count


def _dict_get(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _clean_text(text: str) -> str:
    """Strip markdown code fences that some models wrap around JSON."""
    if not text:
        return ""
    cleaned = text.strip()
    cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*```$', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _get_api_key() -> str | None:
    return (
        config.dashscope_api_key
        or os.getenv("DASHSCOPE_API_KEY")
        or os.getenv("VELA_DASHSCOPE_API_KEY")
    )


def _get_response_text(response_data: Any) -> str:
    if response_data is None:
        return ""
    output = _dict_get(response_data, "output")
    if output is not None:
        text = _dict_get(output, "text")
        if text:
            return _clean_text(str(text))
        choices = _dict_get(output, "choices") or []
        if isinstance(choices, dict):
            choices = [choices]
        for choice in choices:
            if choice is None:
                continue
            message = _dict_get(choice, "message")
            if not message:
                continue
            content = _dict_get(message, "content") or _dict_get(message, "text")
            if content:
                return _clean_text(str(content))
    if isinstance(response_data, dict):
        return _clean_text(json.dumps(response_data))
    return _clean_text(str(response_data))


def _set_dashscope_base_url() -> None:
    """Resolve and set the DashScope base URL. Called once at startup."""
    api_url = (
        os.getenv("DASHSCOPE_HTTP_BASE_URL")
        or os.getenv("DASHSCOPE_API_URL")
        or os.getenv("VELA_DASHSCOPE_API_URL")
        or config.dashscope_api_url
    )
    if "/chat/completions" in api_url:
        api_url = api_url.split("/chat/completions")[0]
    if api_url.startswith("https://api.dashscope.com"):
        api_url = api_url.replace("https://api.dashscope.com", "https://dashscope-intl.aliyuncs.com/api")
    if api_url.startswith("https://dashscope-intl.aliyuncs.com/v1"):
        api_url = api_url.replace("https://dashscope-intl.aliyuncs.com/v1", "https://dashscope-intl.aliyuncs.com/api/v1")
    dashscope.base_http_api_url = api_url.rstrip("/")


_set_dashscope_base_url()


def _extract_json_array(text: str) -> list[dict[str, Any]] | None:
    """
    Extract a JSON array from the model's response.
    Falls back to wrapping a single object in a list for robustness.
    """
    cleaned = _clean_text(text)

    match = re.search(r"\[.*\]", cleaned, flags=re.DOTALL)
    if match:
        candidate = match.group(0)
        try:
            result = json.loads(candidate)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            try:
                candidate = re.sub(r",\s*\]\s*$", "]", candidate)
                candidate = re.sub(r",\s*}\s*]", "}]", candidate)
                result = json.loads(candidate)
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass

    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        try:
            obj = json.loads(match.group(0))
            if isinstance(obj, dict) and "tool" in obj:
                return [obj]
        except json.JSONDecodeError:
            pass

    return None


def _get_or_init_session(user_id: str) -> list[dict[str, str]]:
    if user_id not in SESSION_STORE:
        SESSION_STORE[user_id] = []
    return SESSION_STORE[user_id]


def _trim_history(history: list[dict[str, str]], max_chars: int = MAX_HISTORY_CHARS) -> list[dict[str, str]]:
    """Keep the most recent messages that fit within max_chars."""
    total = 0
    trimmed: list[dict[str, str]] = []
    for msg in reversed(history):
        total += len(msg["content"])
        if total > max_chars:
            break
        trimmed.insert(0, msg)
    return trimmed


def _plan_tool_calls(user_message: str, history: list[dict[str, str]] | None = None) -> list[dict[str, Any]]:
    """
    Single LLM call → list of tool calls to execute in parallel.
    For conversational replies returns a single-item list with tool="none".
    Token cost is the same whether the user asks for 1 or 5 simultaneous actions.
    """
    messages = [{"role": "system", "content": SYSTEM_TOOL_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    response = Generation.call(
        api_key=_get_api_key(),
        model=config.dashscope_model,
        messages=messages,
        result_format="message",
        stream=False,
        incremental_output=False,
        temperature=0.0,
        max_tokens=512,
    )
    text = _get_response_text(response)
    parsed = _extract_json_array(text)
    if not parsed:
        raise ValueError(f"Could not parse tool selection from model output: {text}")
    return parsed


def _compose_final_reply(user_message: str, results: list[dict[str, Any]]) -> tuple[str, str | None]:
    """
    Second LLM call — summarises ALL tool results into one clean Markdown reply.
    Returns (reply_text, art_url) where art_url is present for media status queries.
    Called only when at least one real tool was executed.
    """
    if len(results) == 1 and results[0].get("tool") == "get_media_status":
        media = results[0].get("result") or {}
        title = media.get("title") or "The current track"
        artist = media.get("artist")
        status = (media.get("status") or "unknown").lower()
        position_seconds = media.get("position_seconds")
        length_seconds = media.get("length_seconds")
        art_url = media.get("art_url")

        def _format_time(seconds: Any) -> str | None:
            if seconds is None:
                return None
            try:
                total_seconds = max(0, int(round(float(seconds))))
            except (TypeError, ValueError):
                return None
            minutes, remaining_seconds = divmod(total_seconds, 60)
            if minutes:
                return f"{minutes}:{remaining_seconds:02d}"
            return f"{remaining_seconds}s"

        elapsed_text = _format_time(position_seconds)
        length_text = _format_time(length_seconds)
        heading = f"{title} by {artist}" if artist else str(title)

        parts = [f"**{heading}** is {status}."]
        if elapsed_text:
            parts.append(f"Elapsed: {elapsed_text}.")
        if length_text:
            parts.append(f"Length: {length_text}.")
        return " ".join(parts), art_url

    system = (
        "You are Vela. The user asked for one or more actions. "
        "Use the tool results below to write a single concise Markdown reply. "
        "Do not return raw JSON. If any action failed, say so clearly."
    )
    results_text = "\n".join(
        f"Tool: {r['tool']}\nResult: {json.dumps(r['result'], separators=(',', ':'))}"
        + (f"\nError: {r['error']}" if r.get("error") else "")
        for r in results
    )
    response = Generation.call(
        api_key=_get_api_key(),
        model=config.dashscope_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"User request: {user_message}\n\n{results_text}\n\nAnswer in clean Markdown."},
        ],
        result_format="message",
        stream=False,
        incremental_output=False,
        temperature=0.2,
        max_tokens=512,
    )
    return _get_response_text(response), None


async def _execute_tool(
    app: FastAPI,
    tool_name: str,
    tool_input: dict[str, Any],
    auth_header: str | None,
    confirmed: bool = False,
) -> dict[str, Any]:
    if tool_name not in TOOL_DEFINITIONS:
        raise ValueError(f"Unknown tool: {tool_name}")

    tool = TOOL_DEFINITIONS[tool_name]
    path = tool["path"]

    if tool_name == "kill_process_by_name":
        name = tool_input.get("name")
        if not name:
            raise ValueError("tool_input.name is required for kill_process_by_name")
        path = path.format(name=quote_plus(str(name)))
        tool_input = {}

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


async def _execute_tool_safe(
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
