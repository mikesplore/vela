import asyncio
import json
import logging
import re
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, AsyncGenerator

from dotenv import dotenv_values
from httpx import AsyncClient

from app.domain.assistant import AssistantResponse
from app.services.assistant.safety import (
    PendingAction,
    build_confirmation_card,
)
from app.services.assistant.tools import build_system_tool_prompt
from app.services import capabilities as capabilities_service
from app.utils.config import get_config

config = get_config()
logger = logging.getLogger("vela.assistant")


def clean_text(text: str) -> str:
    """Strip markdown code fences and Qwen3/inline <think> blocks from text."""
    if not text:
        return ""
    cleaned = text.strip()
    # Qwen3 and some models leak thinking as <think>...</think> in the content field
    cleaned = re.sub(r'<think>.*?</think>', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*```$', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def fireworks_stream_delta(chunk: dict[str, Any]) -> dict[str, Any]:
    """Extract the delta dict from a Fireworks/OpenAI-style streaming chunk.

    Some providers emit SSE frames with ``choices: []`` (metadata/keepalive).
    Treat those as empty deltas instead of crashing.
    """
    choices = chunk.get("choices")
    if not choices:
        return {}
    first = choices[0]
    if not isinstance(first, dict):
        return {}
    delta = first.get("delta")
    return delta if isinstance(delta, dict) else {}


def get_api_key() -> str | None:
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


def explain_fireworks_issue(info: Any) -> str:
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


def format_media_time(seconds: Any) -> str | None:
    """Format playback position/length for human-readable replies."""
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


def format_media_playback_summary(media: dict[str, Any]) -> str:
    """Structured now-playing facts — used to keep timing accurate in LLM replies."""
    title = media.get("title") or "Unknown track"
    artist = media.get("artist")
    status = (media.get("status") or "unknown").lower()
    elapsed = format_media_time(media.get("position_seconds"))
    length = format_media_time(media.get("length_seconds"))
    heading = f"{title} by {artist}" if artist else str(title)

    parts = [f"**{heading}** is {status}."]
    if elapsed:
        parts.append(f"Elapsed: {elapsed}.")
    if length:
        parts.append(f"Length: {length}.")
    return " ".join(parts)


def extract_media_playback_context(results: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    """Return (art_url, formatted_summary) when the only tool result is now-playing."""
    if len(results) != 1 or results[0].get("tool") != "get_currently_playing_song":
        return None, None
    media = results[0].get("result") or {}
    if not isinstance(media, dict):
        return None, None
    art_url = media.get("art_url")
    return art_url, format_media_playback_summary(media)


def _build_planner_messages(
    user_message: str,
    history: list[dict[str, str]] | None = None,
    available_tools: set[str] | None = None,
    selected_domains: list[str] | None = None,
) -> list[dict[str, str]]:
    """Build the message list for the tool planner.

    When selected_domains is provided, use the selector stage filtered by those domains.
    Otherwise, fall back to the legacy unfiltered tool list.
    """
    if selected_domains is not None:
        tool_prompt = build_system_tool_prompt(
            available_tools=available_tools,
            stage="selector",
            selected_domains=selected_domains,
        )
    else:
        tool_prompt = build_system_tool_prompt(available_tools=available_tools)
    messages = [
        {"role": "system", "content": config.assistant_system_prompt},
        {"role": "system", "content": tool_prompt},
    ]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})
    return messages


async def plan_domain_selection(user_message: str, history: list[dict[str, str]] | None = None) -> list[str]:
    """Stage 1: Select relevant domains for the user's request.

    Returns a list of domain names, or an empty list for conversational requests.
    """
    messages = [
        {"role": "system", "content": config.assistant_system_prompt},
        {"role": "system", "content": build_system_tool_prompt(stage="router")},
    ]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    api_key = get_api_key()
    if not api_key:
        return []

    url = f"{config.fireworks_api_url}/chat/completions"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": config.fireworks_model,
        "max_tokens": 256,
        "max_completion_tokens": 512,
        "response_format": {"type": "json_object"},
        "messages": messages,
        "top_k": 1,
        "reasoning_history": "disabled",
        "safe_tokenization": True,
    }

    try:
        async with AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            res_json = response.json()
            text = res_json["choices"][0]["message"]["content"] or ""
    except Exception as exc:
        logger.error("Domain selection failed: %s", exc, exc_info=True)
        return []

    clean = clean_text(text)
    try:
        data = json.loads(clean)
        domains = data.get("domains", [])
        if isinstance(domains, list):
            return [str(d) for d in domains if isinstance(d, str)]
    except (json.JSONDecodeError, ValueError):
        pass
    return []


async def plan_tool_calls(user_message: str, history: list[dict[str, str]] | None = None) -> list[dict[str, Any]]:
    """
    Two-stage planner: domain selection → tool selection.
    Single LLM call for conversational replies, two calls for tool requests.
    For conversational replies returns a single-item list with tool="none".
    """
    available_tools = capabilities_service.get_available_tool_names()

    # Stage 1: Domain selection
    selected_domains = await plan_domain_selection(user_message, history)
    if not selected_domains:
        # No domains selected — treat as conversational
        return [{"tool": "none", "tool_input": {}, "conversational_reply": "Hello! How can I help you today?"}]

    # Stage 2: Tool selection filtered by domains
    messages = _build_planner_messages(
        user_message,
        history,
        available_tools=available_tools,
        selected_domains=selected_domains,
    )

    api_key = get_api_key()
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
                    "max_completion_tokens": 1500,
                    "response_format": {"type": "json_object"},
                    "messages": messages,
                    "top_k": 1,
                    "reasoning_history": "disabled",
                    "safe_tokenization": True,
                }

                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()

                res_json = response.json()
                text = res_json["choices"][0]["message"]["content"] or ""
            except Exception as exc:
                logger.error("Fireworks AI chat.completions.create failed: %s", exc, exc_info=True)
                raise ValueError(explain_fireworks_issue(exc)) from exc

            clean = clean_text(text)
            parsed = extract_json_array(clean)
            if parsed:
                normalized = normalize_planner_tool_calls(parsed, available_tools=available_tools)
                if normalized:
                    return normalized

            logger.warning(
                "Model returned non-array JSON on attempt %d/%d. Retrying with correction. Output: %s",
                attempt + 1,
                max_retries,
                clean[:200],
            )
            if attempt < max_retries - 1:
                messages.append({"role": "assistant", "content": clean or text})
                messages.append({
                    "role": "user",
                    "content": (
                        "ERROR: Your previous response was not a valid tool-call JSON array. "
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


async def plan_conditional_followup(
        original_request: str,
        inspection_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Plan one action-only follow-up after a conditional inspection stage."""
    from app.services.assistant.tool_exec import sanitize_tool_results_for_llm

    safe_results = sanitize_tool_results_for_llm(inspection_results)
    results_text = "\n".join(
        f"Tool: {item['tool']}\nResult: {json.dumps(item['result'], separators=(',', ':'))}"
        + (f"\nError: {item['error']}" if item.get("error") else "")
        for item in safe_results
    )
    followup_prompt = (
        "This is the action stage of a two-stage conditional request. "
        "Use the inspection results below to decide which branch of the original request applies. "
        "Return only the required actions; do not repeat the inspection tools. "
        "If no condition is met, return tool='none' with a concise explanation.\n\n"
        f"Original request:\n{original_request}\n\n"
        f"Inspection results:\n{results_text}"
    )
    return await plan_tool_calls(followup_prompt)


async def compose_final_reply(user_message: str, results: list[dict[str, Any]]) -> tuple[str, str | None]:
    """
    Second LLM call — summarises tool results into a human reply.
    Returns (reply_text, art_url) where art_url is present for media status queries.
    """
    from app.services.assistant.tool_exec import sanitize_tool_results_for_llm

    art_url, media_summary = extract_media_playback_context(results)

    system = config.assistant_system_prompt
    safe_results = sanitize_tool_results_for_llm(results)
    results_text = "\n".join(
        f"Tool: {r['tool']}\nResult: {json.dumps(r['result'], separators=(',', ':'))}"
        + (f"\nError: {r['error']}" if r.get("error") else "")
        for r in safe_results
    )
    media_block = ""
    if media_summary:
        media_block = (
            f"\nNow playing (use these exact facts — title, artist, status, elapsed, length):\n"
            f"{media_summary}\n"
        )
    def _looks_like_tool_plan(text_value: str) -> bool:
        if not text_value:
            return False
        cleaned_value = clean_text(text_value)
        return extract_json_array(cleaned_value) is not None

    try:
        api_key = get_api_key()
        if not api_key:
            raise ValueError("FIREWORKS_API_KEY is not configured in your .env file.")

        url = f"{config.fireworks_api_url}/chat/completions"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        # Optimized payload for token-efficient final reply
        payload = {
            "model": config.fireworks_model,
            "max_tokens": 1024,
            "max_completion_tokens": 1500,  # Safety cap for final replies
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",
                 "content": (
                     f"User request: {user_message}\n\n{results_text}"
                     f"{media_block}\n"
                     "Reply in plain Markdown with Vela's voice — short, human, not corporate. "
                     "You can react (praise, roast, joke) when it fits the tool results. "
                     "Any URL must be a Markdown hyperlink [label](url), never bare."
                 )},
            ],
            "top_k": 1,  # More deterministic, reduces token waste
            "reasoning_history": "disabled",  # Keeps inputs from snowballing
            "safe_tokenization": True,
        }

        async with AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()

            res_json = response.json()
            text = res_json["choices"][0]["message"]["content"] or ""

            # Some models occasionally "fall back" into returning a tool plan JSON array
            # even though this is the post-tool summary stage. Retry once with a hard correction.
            if _looks_like_tool_plan(text):
                correction_messages = payload["messages"] + [
                    {"role": "assistant", "content": text},
                    {
                        "role": "user",
                        "content": (
                            "ERROR: You responded with JSON/tool calls. That breaks the app. "
                            "Reply with ONLY the final user-facing Markdown summary. "
                            "No JSON. No arrays/objects. Do not mention tool names. "
                            "If something is missing, ask one short question."
                        ),
                    },
                ]
                retry_payload = dict(payload)
                retry_payload["messages"] = correction_messages
                retry_response = await client.post(url, headers=headers, json=retry_payload)
                retry_response.raise_for_status()
                retry_json = retry_response.json()
                text = retry_json["choices"][0]["message"]["content"] or ""
    except Exception as exc:
        logger.error("Fireworks AI chat.completions.create failed: %s", exc, exc_info=True)
        raise ValueError(explain_fireworks_issue(exc)) from exc
    return clean_text(text), art_url


def split_think_stream(text: str):
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


async def stream_llm_response(
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
    api_key = get_api_key()
    if not api_key:
        yield {"type": "error", "text": "FIREWORKS_API_KEY is not configured in your .env file."}
        return

    url = f"{config.fireworks_api_url}/chat/completions"
    headers = {
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    # Optimized payload for token efficiency
    payload: dict[str, Any] = {
        "model": config.fireworks_model,
        "max_tokens": max_tokens,
        "max_completion_tokens": 1500,  # Overall safety cap for entire response
        "stream": True,
        "messages": messages,
        "top_k": 1,  # More deterministic, reduces token waste
        "reasoning_history": "disabled",  # Keeps inputs from snowballing in cost
        "safe_tokenization": True,
    }
    if enable_thinking:
        payload["thinking"] = {"type": "enabled", "budget_tokens": 1024}  # Hard cap to stop overthinking

    yielded_anything = False
    in_think_block = False
    try:
        # 300 second timeout for streaming LLM responses (5 minutes)
        async with AsyncClient(timeout=300.0) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()
                async for raw_line in response.aiter_lines():
                    line = raw_line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        if not yielded_anything:
                            yield {"type": "content", "text": ""}
                        yield {"type": "done"}
                        return
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    delta = fireworks_stream_delta(chunk)
                    if enable_thinking and delta.get("reasoning_content"):
                        yield {"type": "thinking", "text": delta["reasoning_content"]}
                        yielded_anything = True
                    c = delta.get("content")
                    if c:
                        yielded_anything = True
                        chunk_rem = c
                        while chunk_rem:
                            if not in_think_block:
                                open_idx = chunk_rem.lower().find("<think>")
                                if open_idx == -1:
                                    yield {"type": "content", "text": chunk_rem}
                                    break
                                if open_idx > 0:
                                    yield {"type": "content", "text": chunk_rem[:open_idx]}
                                in_think_block = True
                                chunk_rem = chunk_rem[open_idx + 7:]
                            else:
                                close_idx = chunk_rem.lower().find("</think>")
                                if close_idx == -1:
                                    if enable_thinking:
                                        yield {"type": "thinking", "text": chunk_rem}
                                    chunk_rem = ""
                                    break
                                if close_idx > 0:
                                    if enable_thinking:
                                        yield {"type": "thinking", "text": chunk_rem[:close_idx]}
                                in_think_block = False
                                chunk_rem = chunk_rem[close_idx + 8:]
        if not yielded_anything:
            yield {"type": "content", "text": ""}
        yield {"type": "done"}
    except Exception as exc:
        logger.error("Streaming LLM call failed: %s", exc, exc_info=True)
        yield {"type": "error", "text": explain_fireworks_issue(exc)}
        yield {"type": "done"}


async def plan_tool_calls_streaming(
        user_message: str,
        history: list[dict[str, str]] | None = None,
        enable_thinking: bool = False,
) -> AsyncGenerator[dict[str, str] | list[dict[str, Any]], None]:
    """
    Streaming-aware tool planner with two-stage domain routing.

    Yields:
        {"type": "thinking", "text": "..."} — live thinking deltas while planning
        {"type": "planning_done"} — planning finished, JSON parsed
        list[dict] — the parsed tool_calls (single non-dict yield)

    Falls back to the non-streaming planner if streaming JSON can't be assembled.
    Note: response_format/json_object is incompatible with stream=True on Fireworks,
    so we stream with thinking enabled and buffer the content for JSON parsing.
    """
    available_tools = capabilities_service.get_available_tool_names()
    selected_domains = await plan_domain_selection(user_message, history)
    if not selected_domains:
        yield {"type": "planning_done"}
        yield [{"tool": "none", "tool_input": {}, "conversational_reply": "Hello! How can I help you today?"}]
        return
    messages = _build_planner_messages(
        user_message,
        history,
        available_tools=available_tools,
        selected_domains=selected_domains,
    )

    api_key = get_api_key()
    if not api_key:
        raise ValueError("FIREWORKS_API_KEY is not configured in your .env file.")

    url = f"{config.fireworks_api_url}/chat/completions"
    headers = {
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    # Optimized payload for token-efficient streaming tool planning
    payload: dict[str, Any] = {
        "model": config.fireworks_model,
        "max_tokens": 512,
        "max_completion_tokens": 800,  # Safety cap for planning responses
        "stream": True,
        "messages": messages,
        "top_k": 1,  # More deterministic, reduces token waste
        "reasoning_history": "disabled",  # Keeps inputs from snowballing in cost
        "safe_tokenization": True,
    }
    if enable_thinking:
        payload["thinking"] = {"type": "enabled", "budget_tokens": 1024}

    content_buf = ""
    reasoning_buf = ""
    max_retries = 4
    last_unescaped = ""
    detected_tools: set[str] = set()

    for attempt in range(max_retries):
        content_buf = ""
        reasoning_buf = ""
        # DO NOT clear detected_tools or last_unescaped here!
        # They persist across retries to prevent duplicate events.
        try:
            # 300 second timeout for streaming tool planner (5 minutes)
            async with AsyncClient(timeout=300.0) as client:
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
                        delta = fireworks_stream_delta(chunk)
                        if enable_thinking and delta.get("reasoning_content"):
                            yield {"type": "thinking", "text": delta["reasoning_content"]}
                        if delta.get("reasoning_content"):
                            reasoning_buf += str(delta["reasoning_content"])
                        if delta.get("content"):
                            # Buffer raw content for JSON parsing
                            for evt in split_think_stream(delta["content"]):
                                if enable_thinking and evt["type"] == "thinking":
                                    yield evt
                                elif evt["type"] == "content":
                                    content_buf += evt["text"]

                                    # Try to stream conversational_reply
                                    marker = '"conversational_reply":"'
                                    m_idx = content_buf.find(marker)
                                    if m_idx != -1:
                                        start_pos = m_idx + len(marker)
                                        val_part = content_buf[start_pos:]
                                        # Find first unescaped "
                                        end_match = re.search(r'(?<!\\)"', val_part)
                                        if end_match:
                                            val_part = val_part[:end_match.start()]

                                        try:
                                            # Partial unescape logic
                                            current_unescaped = json.loads('"' + (val_part[:-1] if val_part.endswith('\\') else val_part) + '"')
                                            if len(current_unescaped) > len(last_unescaped):
                                                new_text = current_unescaped[len(last_unescaped):]
                                                yield {"type": "content", "text": new_text}
                                                last_unescaped = current_unescaped
                                        except Exception:
                                            pass

                                        # Try to detect tool calls early
                                        for tname in re.findall(r'"tool"\s*:\s*"([^"]+)"', content_buf):
                                            if tname not in detected_tools and tname != "none":
                                                yield {"type": "tool_detected", "text": tname}
                                                detected_tools.add(tname)
        except Exception as exc:
            logger.error("Streaming tool planner failed on attempt %d: %s", attempt + 1, exc, exc_info=True)
            if attempt == max_retries - 1:
                raise ValueError(explain_fireworks_issue(exc)) from exc
            await asyncio.sleep(1)
            continue

        parsed = extract_json_array(clean_text(content_buf))
        if not parsed and reasoning_buf:
            # Some models/providers send the entire answer into `reasoning_content` while leaving `content` empty.
            parsed = extract_json_array(clean_text(reasoning_buf))
        if parsed:
            normalized = normalize_planner_tool_calls(parsed, available_tools=available_tools)
            if not normalized:
                parsed = None
            else:
                parsed = normalized
        if parsed:
            yield {"type": "planning_done"}
            yield parsed  # type: ignore[misc]
            return

        logger.warning(
            "Planner non-array JSON on attempt %d/%d. Output: %s",
            attempt + 1, max_retries, content_buf[:200],
        )
        if attempt < max_retries - 1:
            messages.append({"role": "assistant", "content": content_buf or reasoning_buf})
            messages.append({
                "role": "user",
                "content": (
                    "ERROR: Your previous response was not a valid tool-call JSON array. "
                    "You MUST respond with ONLY a JSON array starting with '[' and ending with ']'. "
                    "No markdown, no explanations, no natural language. "
                    'Example: [{"tool":"none","tool_input":{},"conversational_reply":"Your reply here"}]'
                ),
            })

    # Final fallback: try a single non-streaming plan (response_format json_object) before giving up.
    # Use the *mutated* messages list so the model sees the prior failures + correction prompt.
    try:
        api_key = get_api_key()
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
            "max_completion_tokens": 1500,
            "response_format": {"type": "json_object"},
            "messages": messages,
            "top_k": 1,
            "reasoning_history": "disabled",
            "safe_tokenization": True,
        }
        async with AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            res_json = response.json()
            text = res_json["choices"][0]["message"]["content"] or ""

        parsed = extract_json_array(clean_text(text))
        if parsed:
            yield {"type": "planning_done"}
            yield parsed  # type: ignore[misc]
            return
    except Exception:
        pass

    logger.error("Planner failed after %d retries. Output: %s", max_retries, content_buf[:500])
    yield {"type": "planning_done"}
    yield [{"tool": "none", "tool_input": {}, "conversational_reply": "I'm sorry, I couldn't process that request. Please try rephrasing it."}]  # type: ignore[misc]


def extract_json_array(text: str) -> list[dict[str, Any]] | None:
    """
    Extract a JSON array from the model's response.
    Falls back to wrapping a single object in a list for robustness.
    """
    cleaned = clean_text(text)

    match = re.search(r"\[.*\]", cleaned, flags=re.DOTALL)
    if match:
        candidate = match.group(0)
        try:
            result = json.loads(candidate)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            try:
                candidate = re.sub(r",\s*]\s*$", "]", candidate)
                candidate = re.sub(r",\s*}\s*]", "}]", candidate)
                result = json.loads(candidate)
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass

    match = re.search(r"\{.*}", cleaned, flags=re.DOTALL)
    if match:
        try:
            obj = json.loads(match.group(0))
            if isinstance(obj, dict) and "tool" in obj:
                return [obj]
        except json.JSONDecodeError:
            pass

    return None


def normalize_planner_tool_calls(
    tool_calls: list[dict[str, Any]] | None,
    *,
    available_tools: set[str] | None = None,
) -> list[dict[str, Any]] | None:
    """Normalize the planner output into the canonical tool-call list shape.

    Some models occasionally:
    - Put a JSON tool plan inside conversational_reply (as a string).
    - Return a list with missing/invalid tool_input.
    - "Explain" a tool call in conversational_reply while setting tool="none".

    Returning None signals "treat this as invalid, retry planning".
    """
    if not tool_calls:
        return None

    # Salvage: tool plan accidentally embedded inside conversational_reply.
    for item in tool_calls:
        if not isinstance(item, dict):
            continue
        if item.get("tool") != "none":
            continue
        reply = item.get("conversational_reply")
        if not isinstance(reply, str) or not reply.strip():
            continue
        embedded = extract_json_array(reply)
        if embedded and any(
            isinstance(call, dict) and call.get("tool") and call.get("tool") != "none"
            for call in embedded
        ):
            tool_calls = embedded
            break

    normalized: list[dict[str, Any]] = []
    for item in tool_calls:
        if not isinstance(item, dict):
            continue
        tool = item.get("tool")
        if not tool:
            continue
        tool_name = str(tool)

        tool_input = item.get("tool_input") or {}
        if not isinstance(tool_input, dict):
            tool_input = {}

        normalized_item: dict[str, Any] = {"tool": tool_name, "tool_input": tool_input}

        if "depends_on" in item:
            normalized_item["depends_on"] = item["depends_on"]
        if "conversational_reply" in item and item.get("conversational_reply") is not None:
            normalized_item["conversational_reply"] = str(item.get("conversational_reply"))

        normalized.append(normalized_item)

    if not normalized:
        return None

    # If the model "described" a tool call but didn't emit it, force a retry.
    if len(normalized) == 1 and normalized[0].get("tool") == "none":
        reply = str(normalized[0].get("conversational_reply") or "")
        if reply:
            suspicious = bool(
                re.search(r'"tool"\s*:', reply)
                or re.search(r"\btool_input\b", reply)
                or re.search(r"\bgatekeeper_\w+\b", reply)
            )
            if suspicious:
                if available_tools and any(t in reply for t in available_tools):
                    return None
                if not available_tools:
                    return None

    return normalized


def expires_in_s(expires_at: datetime) -> int:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return max(0, int((expires_at - datetime.now(UTC)).total_seconds()))


def pending_response(pending: PendingAction) -> AssistantResponse:
    expires_in_seconds = expires_in_s(pending.expires_at)
    confirmation_card = build_confirmation_card(
        pending.tool_calls,
        pending.requires_auth,
        pin_attempts=pending.pin_attempts,
    )
    return AssistantResponse(
        reply=pending.prompt,
        pending_action_id=pending.action_id,
        requires_confirmation=not pending.requires_auth,
        requires_auth=pending.requires_auth,
        expires_in_seconds=expires_in_seconds,
        confirmation=confirmation_card,
    )


# Re-exports for backwards-compatible imports from helpers
from app.services.assistant.session import (  # noqa: E402
    MAX_HISTORY_CHARS,
    SESSION_STORE,
    extract_session_id,
    get_or_init_session,
    trim_history,
)
from app.services.assistant.tool_exec import (  # noqa: E402
    _execute_tool,
    execute_tool_calls,
    execute_tool_safe,
)
