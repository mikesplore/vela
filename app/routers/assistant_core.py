import asyncio
import base64
import json
import logging
import re
from typing import Any, AsyncGenerator
from pathlib import Path
from dotenv import dotenv_values
from urllib.parse import quote_plus

from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from app.config import Config
from .assistant_tools import INPUT_CONFIRM_TOOLS, SYSTEM_TOOL_PROMPT, TOOL_ALIASES, TOOL_DEFINITIONS

config = Config()
logger = logging.getLogger("vela.assistant")

# In-memory session store: {user_id: [{"role": "user|assistant", "content": "..."}, ...]}
SESSION_STORE: dict[str, list[dict[str, str]]] = {}
MAX_HISTORY_CHARS = 4000  # Token-budget-aware trimming instead of message count


def _clean_text(text: str) -> str:
    """Strip markdown code fences and Qwen3/inline <think> blocks from text."""
    if not text:
        return ""
    cleaned = text.strip()
    # Qwen3 and some models leak thinking as <think>...</think> in the content field
    cleaned = re.sub(r'<think>.*?</think>', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*```$', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _get_api_key() -> str | None:
    """Read FIREWORKS_API_KEY strictly from dotfiles only.

    Search order (first match wins):
    1. ./ .env
    2. ~/.config/vela/.env
    3. package_dir/.env

    Do NOT read from process environment or config.yaml.
    """
    candidate_paths = [
        Path.cwd() / ".env",
        Path.home() / ".config" / "vela" / ".env",
        Path(__file__).resolve().parent / ".env",
    ]

    for p in candidate_paths:
        try:
            if not p.exists():
                continue
            vals = dotenv_values(p)
        except Exception:
            continue
        key = vals.get("FIREWORKS_API_KEY")
        if key:
            return str(key)
    return None


def _explain_fireworks_issue(info: Any) -> str:
    """Return a concise, user-facing explanation for Fireworks AI errors.

    Accepts either an Exception or a response-like dict/object.
    """
    try:
        if isinstance(info, Exception):
            msg = str(info)
            lower = msg.lower()
            if "401" in msg or "unauthorized" in lower or "api key" in lower:
                return "Authentication failed: missing or invalid FIREWORKS_API_KEY in your .env file."
            if "429" in msg or "rate limit" in lower:
                return "Rate limited: too many requests to Fireworks AI. Try again later."
            if "timeout" in lower:
                return "Request timed out contacting the Fireworks AI API. Check network connectivity."
            return f"Error contacting Fireworks AI: {msg}"

        if isinstance(info, dict):
            err = info.get("error") or info.get("message") or info
            if isinstance(err, dict):
                code = err.get("code") or err.get("status")
                message = err.get("message") or err.get("detail") or str(err)
                code_str = str(code) if code is not None else ""
                if "401" in code_str or "401" in message:
                    return "Authentication failed: invalid FIREWORKS_API_KEY in your .env file."
                if "429" in code_str or "rate" in message.lower():
                    return "Rate limited: too many requests to Fireworks AI. Try again later."
                if code and int(code) >= 500:
                    return "Fireworks AI service error: the remote service is unavailable. Try again later."
                return f"Fireworks AI API error: {message}"
            return f"Fireworks AI error: {err}"
    except Exception:
        pass
    return "An unknown error occurred while contacting Fireworks AI."


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


async def _plan_tool_calls(user_message: str, history: list[dict[str, str]] | None = None) -> list[dict[str, Any]]:
    """
    Single LLM call → list of tool calls to execute in parallel.
    For conversational replies returns a single-item list with tool="none".
    Token cost is the same whether the user asks for 1 or 5 simultaneous actions.
    """
    messages = [{"role": "system", "content": SYSTEM_TOOL_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    api_key = _get_api_key()
    if not api_key:
        raise ValueError("FIREWORKS_API_KEY is not configured in your .env file.")

    url = f"{config.fireworks_api_url}/chat/completions"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    max_retries = 4
    text = ""
    async with AsyncClient(timeout=30.0) as client:
        for attempt in range(max_retries):
            try:
                payload = {
                    "model": config.fireworks_model,
                    "max_tokens": 1024,
                    "response_format": {"type": "json_object"},
                    "messages": messages,
                }

                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()

                res_json = response.json()
                text = res_json["choices"][0]["message"]["content"] or ""
            except Exception as exc:
                logger.error("Fireworks AI chat.completions.create failed: %s", exc, exc_info=True)
                raise ValueError(_explain_fireworks_issue(exc)) from exc

            # Strip think blocks before any parsing or history injection
            clean = _clean_text(text)
            parsed = _extract_json_array(clean)
            if parsed:
                return parsed

            logger.warning(
                "Model returned non-array JSON on attempt %d/%d. Retrying with correction. Output: %s",
                attempt + 1,
                max_retries,
                clean[:200],
            )
            if attempt < max_retries - 1:
                # Append the CLEANED text (no <think> blocks) so retries don't get poisoned
                messages.append({"role": "assistant", "content": clean or text})
                messages.append({
                    "role": "user",
                    "content": (
                        "ERROR: Your previous response was not a JSON array. "
                        "You MUST respond with ONLY a JSON array starting with '[' and ending with ']'. "
                        "No markdown, no explanations, no natural language. "
                        'Example: [{"tool":"none","tool_input":{},"conversational_reply":"Your reply here"}]'
                    ),
                })

    logger.error(
        "Could not parse tool selection from model output after %d retries. Output: %s",
        max_retries,
        text[:500],
    )
    return [{"tool": "none", "tool_input": {}, "conversational_reply": "I'm sorry, I couldn't process that request. Please try rephrasing it."}]


async def _compose_final_reply(user_message: str, results: list[dict[str, Any]]) -> tuple[str, str | None]:
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

    system = config.assistant_system_prompt
    results_text = "\n".join(
        f"Tool: {r['tool']}\nResult: {json.dumps(r['result'], separators=(',', ':'))}"
        + (f"\nError: {r['error']}" if r.get("error") else "")
        for r in results
    )
    try:
        api_key = _get_api_key()
        if not api_key:
            raise ValueError("FIREWORKS_API_KEY is not configured in your .env file.")

        url = f"{config.fireworks_api_url}/chat/completions"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        payload = {
            "model": config.fireworks_model,
            "max_tokens": 1024,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",
                 "content": f"User request: {user_message}\n\n{results_text}\n\nAnswer in clean Markdown."},
            ],
        }

        async with AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()

            res_json = response.json()
            text = res_json["choices"][0]["message"]["content"] or ""
    except Exception as exc:
        logger.error("Fireworks AI chat.completions.create failed: %s", exc, exc_info=True)
        raise ValueError(_explain_fireworks_issue(exc)) from exc
    return _clean_text(text), None



def _split_think_stream(text: str):
    """
    Qwen3 and some models emit <think>...</think> inline in the content delta stream.
    This splits a single delta chunk into typed events so the streaming handlers
    can route thinking tokens to the thinking event and real content separately.

    Handles partial tags across chunk boundaries by treating an unclosed <think>
    as a thinking token (safe: worst case a thinking fragment leaks into content).

    Yields dicts: {"type": "thinking"|"content", "text": "..."}
    """
    remaining = text
    while remaining:
        open_idx = remaining.lower().find("<think>")
        if open_idx == -1:
            # No think tag — check if it ends with a partial open tag
            # e.g. chunk ends with "<thi" — safe to pass through as content
            if remaining:
                yield {"type": "content", "text": remaining}
            break

        # Content before the <think> tag
        if open_idx > 0:
            yield {"type": "content", "text": remaining[:open_idx]}
        remaining = remaining[open_idx + 7:]  # skip "<think>"

        close_idx = remaining.lower().find("</think>")
        if close_idx == -1:
            # Unclosed tag — rest of this chunk is thinking
            if remaining:
                yield {"type": "thinking", "text": remaining}
            break

        if close_idx > 0:
            yield {"type": "thinking", "text": remaining[:close_idx]}
        remaining = remaining[close_idx + 8:]  # skip "</think>"


async def _stream_llm_response(
        messages: list[dict[str, Any]],
        max_tokens: int = 1024,
        enable_thinking: bool = True,
) -> AsyncGenerator[dict[str, str], None]:
    """
    Stream a Fireworks chat completion, yielding structured delta dicts:
        {"type": "thinking", "text": "..."}   — reasoning_content chunk
        {"type": "content",  "text": "..."}   — visible answer chunk
        {"type": "done"}                       — stream finished

    Thinking is enabled via the `thinking` parameter (V4 Flash compatible).
    This is NOT used for the tool planner (JSON mode is incompatible with streaming).
    """
    api_key = _get_api_key()
    if not api_key:
        yield {"type": "error", "text": "FIREWORKS_API_KEY is not configured in your .env file."}
        return

    url = f"{config.fireworks_api_url}/chat/completions"
    headers = {
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload: dict[str, Any] = {
        "model": config.fireworks_model,
        "max_tokens": max_tokens,
        "stream": True,
        "messages": messages,
    }
    if enable_thinking:
        payload["thinking"] = {"type": "enabled", "budget_tokens": 2048}

    try:
        async with AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()
                async for raw_line in response.aiter_lines():
                    line = raw_line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        yield {"type": "done"}
                        return
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    # Dedicated reasoning_content field (DeepSeek / R1 style)
                    if delta.get("reasoning_content"):
                        yield {"type": "thinking", "text": delta["reasoning_content"]}
                    # Visible content — may contain inline <think> blocks (Qwen3 style)
                    if delta.get("content"):
                        for _evt in _split_think_stream(delta["content"]):
                            yield _evt
    except Exception as exc:
        logger.error("Streaming LLM call failed: %s", exc, exc_info=True)
        yield {"type": "error", "text": _explain_fireworks_issue(exc)}


async def _plan_tool_calls_streaming(
        user_message: str,
        history: list[dict[str, str]] | None = None,
) -> AsyncGenerator[dict[str, str] | list[dict[str, Any]], None]:
    """
    Streaming-aware tool planner.

    Yields:
        {"type": "thinking", "text": "..."}  — live thinking deltas while planning
        {"type": "planning_done"}             — planning finished, JSON parsed
        list[dict]                            — the parsed tool_calls (single non-dict yield)

    Falls back to the non-streaming planner if streaming JSON can't be assembled.
    Note: response_format/json_object is incompatible with stream=True on Fireworks,
    so we stream with thinking enabled and buffer the content for JSON parsing.
    """
    messages = [{"role": "system", "content": SYSTEM_TOOL_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    api_key = _get_api_key()
    if not api_key:
        raise ValueError("FIREWORKS_API_KEY is not configured in your .env file.")

    url = f"{config.fireworks_api_url}/chat/completions"
    headers = {
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload: dict[str, Any] = {
        "model": config.fireworks_model,
        "max_tokens": 512,
        "stream": True,
        "thinking": {"type": "enabled", "budget_tokens": 1024},
        "messages": messages,
    }

    content_buf = ""
    max_retries = 4

    for attempt in range(max_retries):
        content_buf = ""
        try:
            async with AsyncClient(timeout=30.0) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    response.raise_for_status()
                    async for raw_line in response.aiter_lines():
                        line = raw_line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        if delta.get("reasoning_content"):
                            yield {"type": "thinking", "text": delta["reasoning_content"]}
                        if delta.get("content"):
                            # Buffer raw content; also stream any <think> prefix as thinking
                            for evt in _split_think_stream(delta["content"]):
                                if evt["type"] == "thinking":
                                    yield evt
                                # content parts go into the buffer for JSON parsing, not streamed
                                elif evt["type"] == "content":
                                    content_buf += evt["text"]
        except Exception as exc:
            logger.error("Streaming tool planner failed: %s", exc, exc_info=True)
            raise ValueError(_explain_fireworks_issue(exc)) from exc

        parsed = _extract_json_array(_clean_text(content_buf))
        if parsed:
            yield {"type": "planning_done"}
            yield parsed  # type: ignore[misc]
            return

        logger.warning(
            "Planner non-array JSON on attempt %d/%d. Output: %s",
            attempt + 1, max_retries, content_buf[:200],
        )
        if attempt < max_retries - 1:
            messages.append({"role": "assistant", "content": content_buf})
            messages.append({
                "role": "user",
                "content": (
                    "ERROR: Your previous response was not a JSON array. "
                    "You MUST respond with ONLY a JSON array starting with '[' and ending with ']'. "
                    "No markdown, no explanations, no natural language. "
                    'Example: [{"tool":"none","tool_input":{},"conversational_reply":"Your reply here"}]'
                ),
            })

    logger.error("Planner failed after %d retries. Output: %s", max_retries, content_buf[:500])
    yield {"type": "planning_done"}
    yield [{"tool": "none", "tool_input": {}, "conversational_reply": "I'm sorry, I couldn't process that request. Please try rephrasing it."}]  # type: ignore[misc]


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