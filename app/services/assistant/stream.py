"""
Streaming assistant endpoint — POST /assistant/stream

Drop-in replacement for POST /assistant/chat that returns SSE instead of JSON.
Same request body: {"message": "..."}
Same headers:      X-Session-ID, Authorization, X-Secret

SSE event types emitted (in order):
  event: thinking   data: {"text": "..."}        # model reasoning, token-by-token
  event: tool       data: {"name":"...","status":"running"|"done"|"error","result":...}
  event: gate       data: {pending_action_id, requires_auth, confirmation, expires_in_seconds}
  event: content    data: {"text": "..."}         # final reply, token-by-token
  event: art        data: {"url": "..."}          # album art URL (media queries only)
  event: screenshot data: {"image_base64": "..."}
  event: done       data: {}                      # stream finished, safe to close
  event: error      data: {"text": "..."}         # fatal / unrecoverable error

curl example:
  curl -N -s -X POST https://host/assistant/stream \\
    -H "X-Secret: ..." \\
    -H "Content-Type: application/json" \\
    -H "X-Session-ID: my-client-002" \\
    -d '{"message": "max out the volume"}'
"""

import asyncio
import hashlib
import json
from datetime import datetime, UTC
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.services.assistant.tools import TOOL_DISPLAY_NAMES

from app.services.assistant.helpers import (
    plan_tool_calls_streaming,
    stream_llm_response,
    config,
    logger,
    compose_final_reply,
    get_api_key,
    plan_conditional_followup,
)
from app.services.assistant.session import (
    SESSION_STORE,
    get_or_init_session,
    trim_history,
)
from app.services.assistant.tool_exec import (
    download_image_payload,
    execute_tool_audited,
    sanitize_tool_result_for_llm,
)
from app.services.assistant.workflow import (
    needs_conditional_followup,
    next_execution_stage,
    prepare_tool_calls,
)
from app.services.assistant.safety import (
    PIN_MAX_ATTEMPTS,
    build_confirmation_card,
    cancel_pending_action_by_ai,
    clear_pending_action,
    get_pending_action,
    is_affirmative,
    is_negative,
    matches_assistant_pin,
    register_pending_action,
    register_pin_rejection,
    requires_auth,
    requires_gate,
)

router = APIRouter(prefix="/assistant", tags=["assistant"])


# ── Request model (same shape as /chat) ──────────────────────────────────────

class StreamRequest(BaseModel):
    message: str


# ── SSE helpers ───────────────────────────────────────────────────────────────

def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"

def _sse_thinking(text: str) -> str:
    return _sse("thinking", {"text": text})

def _sse_content(text: str) -> str:
    return _sse("content", {"text": text})

def _friendly_tool_name(raw: str) -> str:
    """Map a raw tool identifier to a human-readable display name."""
    return TOOL_DISPLAY_NAMES.get(raw, raw.replace("_", " ").title())


def _sse_tool(name: str, status: str, result: dict | None = None, error: str | None = None) -> str:
    payload: dict = {"name": _friendly_tool_name(name), "status": status}
    if result is not None:
        payload["result"] = result
    if error is not None:
        payload["error"] = error
    return _sse("tool", payload)

def _sse_gate(pending_action_id: str, req_auth: bool, confirmation: dict, expires_in: int) -> str:
    return _sse("gate", {
        "pending_action_id": pending_action_id,
        "requires_confirmation": not req_auth,
        "requires_auth": req_auth,
        "expires_in_seconds": expires_in,
        "confirmation": confirmation,
    })

def _sse_done() -> str:
    return _sse("done", {})

def _sse_error(text: str) -> str:
    return _sse("error", {"text": text})

def _expires_in(expires_at: datetime) -> int:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return max(0, int((expires_at - datetime.now(UTC)).total_seconds()))


# ── Session ID (mirrors assistant.py) ────────────────────────────────────────

def _extract_session_id(request: Request) -> str:
    sid = request.headers.get("X-Session-ID")
    if sid:
        return sid
    device_id = request.headers.get("X-Forwarded-Device-Id") or request.headers.get("X-Device-Id")
    if device_id:
        return device_id
    user_agent = request.headers.get("User-Agent", "unknown")
    forwarded_for = request.headers.get("X-Forwarded-For")
    client_ip = forwarded_for.split(",")[0].strip() if forwarded_for else (
        request.client.host if request.client else "unknown"
    )
    return hashlib.sha256(f"{user_agent}|{client_ip}".encode()).hexdigest()[:16]


# ── Tool execution + streaming reply ─────────────────────────────────────────

async def _run_tools_and_reply(
        request: Request,
        tool_calls: list[dict],
        auth_header: str | None,
        user_message: str,
        history: list[dict],
        current_user: str,
        confirmed: bool,
        enable_thinking: bool = False,
        already_running: set[str] | None = None,
) -> AsyncGenerator[str, None]:
    if already_running is None:
        already_running = set()

    prepared_calls = prepare_tool_calls(tool_calls)
    completed: dict[str, dict] = {}
    tool_results: list[dict] = []

    while len(completed) < len(prepared_calls):
        ready, skipped = next_execution_stage(prepared_calls, completed)
        for call, result in skipped:
            completed[call["id"]] = result
            tool_results.append(result)
            yield _sse_tool(result["tool"], "error", error=result["error"])

        async def _run_call(call: dict) -> tuple[dict, dict]:
            result = await execute_tool_audited(
                request.app,
                call["tool"],
                call["tool_input"],
                auth_header,
                request_id=getattr(request.state, "request_id", None),
                user_id=current_user,
                confirmed=confirmed,
            )
            return call, result

        if ready:
            for call in ready:
                if call["tool"] not in already_running:
                    yield _sse_tool(call["tool"], "running")

            tasks = [_run_call(call) for call in ready]
            for coro in asyncio.as_completed(tasks):
                call, result = await coro
                completed[call["id"]] = result
                tool_results.append(result)
                if result.get("error"):
                    yield _sse_tool(result["tool"], "error", error=result["error"])
                else:
                    yield _sse_tool(result["tool"], "done", result=result.get("result"))

    if needs_conditional_followup(user_message, tool_calls):
        try:
            followup_calls = await plan_conditional_followup(user_message, tool_results)
        except Exception as exc:
            logger.error("Conditional follow-up planning failed: %s", exc, exc_info=True)
        else:
            followup_real_calls = [
                call for call in followup_calls if call.get("tool") and call["tool"] != "none"
            ]
            followup_gated = [
                call for call in followup_real_calls if requires_gate(str(call["tool"]))
            ]
            if followup_gated:
                require_pin = bool(config.assistant_action_pin) and any(
                    requires_auth(str(call["tool"])) for call in followup_gated
                )
                session_id = _extract_session_id(request)
                pending = register_pending_action(
                    current_user,
                    session_id,
                    user_message,
                    followup_real_calls,
                    requires_auth=require_pin,
                )
                card = build_confirmation_card(
                    pending.tool_calls, pending.requires_auth, pin_attempts=pending.pin_attempts
                )
                yield _sse_gate(
                    pending.action_id,
                    pending.requires_auth,
                    card.model_dump(),
                    _expires_in(pending.expires_at),
                )
                yield _sse_content(pending.prompt)
                yield _sse_done()
                return

            if followup_real_calls:
                async for chunk in _run_tools_and_reply(
                    request,
                    followup_real_calls,
                    auth_header,
                    user_message,
                    history,
                    current_user,
                    confirmed=confirmed,
                    enable_thinking=enable_thinking,
                    already_running={result["tool"] for result in tool_results},
                ):
                    yield chunk
                return

    # Deliver downloaded images on the same channel as screenshots (client already handles this).
    for r in tool_results:
        if r.get("tool") != "download_file" or r.get("error"):
            continue
        result = r.get("result") or {}
        if isinstance(result, dict) and result.get("is_image") and result.get("image_base64"):
            yield _sse("screenshot", {"image_base64": result["image_base64"]})

    # Fast-path: screenshot only (no second LLM call — image data is too large)
    if len(tool_results) == 1 and tool_results[0].get("tool") == "display_screenshot":
        result = tool_results[0].get("result") or {}
        img = result.get("image_base64") if isinstance(result, dict) else None
        if img:
            yield _sse("screenshot", {"image_base64": img})
        yield _sse_content("Screenshot captured.")
        history.append({"role": "assistant", "content": "Screenshot captured."})
        SESSION_STORE[current_user] = trim_history(history)
        yield _sse_done()
        return

    # Fast-path: single image download (same as screenshot — skip second LLM call)
    image_download = download_image_payload(tool_results)
    if image_download:
        name, _img = image_download
        reply = f"Here's {name}."
        yield _sse_content(reply)
        history.append({"role": "assistant", "content": reply})
        SESSION_STORE[current_user] = trim_history(history)
        yield _sse_done()
        return

    # Fast-path: media status (no second LLM call needed)
    if len(tool_results) == 1 and tool_results[0].get("tool") == "get_currently_playing_song":
        try:
            reply_text, art_url = await compose_final_reply(user_message, tool_results)
        except Exception as exc:
            reply_text, art_url = str(exc), None
        if art_url:
            yield _sse("art", {"url": art_url})
        yield _sse_content(reply_text)
        history.append({"role": "assistant", "content": reply_text.strip()})
        SESSION_STORE[current_user] = trim_history(history)
        yield _sse_done()
        return

    # Stream the final reply (binary payloads stripped — already sent to client above)
    results_text = ""
    for r in tool_results:
        safe_result = sanitize_tool_result_for_llm(r.get("result"))
        res_str = json.dumps(safe_result, separators=(',', ':'))
        if len(res_str) > 5000:
            res_str = res_str[:5000] + "... [TRUNCATED]"
        results_text += f"\nTool: {r['tool']}\nResult: {res_str}"
        if r.get("error"):
            results_text += f"\nError: {r['error']}"

    reply_messages = [{"role": "system", "content": config.assistant_system_prompt}]
    reply_messages.extend(trim_history(history))
    reply_messages.append({
        "role": "user",
        "content": (
            f"Tool execution results:\n{results_text}\n\n"
            "Final answer for the user. Vela voice: short, human, not corporate — "
            "opinions and jokes ok if grounded in these results. "
            "URLs as Markdown hyperlinks [label](url), never bare."
        ),
    })

    full_reply = ""
    got_content = False
    async for delta in stream_llm_response(reply_messages, max_tokens=1024, enable_thinking=enable_thinking):
        if delta["type"] == "thinking":
            if enable_thinking:
                yield _sse_thinking(delta["text"])
        elif delta["type"] == "content":
            got_content = True
            full_reply += delta["text"]
            yield _sse_content(delta["text"])
        elif delta["type"] == "error":
            yield _sse_error(delta["text"])
            yield _sse_done()
            history.append({"role": "assistant", "content": ""})
            SESSION_STORE[current_user] = trim_history(history)
            return

    # Ensure we always produce at least an empty content event so the client isn't left hanging
    if not got_content:
        yield _sse_content("")

    history.append({"role": "assistant", "content": full_reply.strip()})
    SESSION_STORE[current_user] = trim_history(history)
    yield _sse_done()


# ── Main stream generator ─────────────────────────────────────────────────────

async def stream_chat(request: Request, message: str, current_user: str) -> AsyncGenerator[str, None]:
    if not get_api_key():
        yield _sse_error("FIREWORKS_API_KEY is unavailable.")
        yield _sse_done()
        return

    session_id = _extract_session_id(request)
    auth_header = request.headers.get("authorization")
    history = get_or_init_session(current_user)
    pending = get_pending_action(current_user, session_id)

    # ── Pending-action state machine ─────────────────────────────────────────
    if pending:
        msg = message.strip()

        if is_negative(msg):
            clear_pending_action(current_user, session_id)
            history = [h for h in history if h.get("content") != pending.user_message]
            SESSION_STORE[current_user] = history
            yield _sse_content("Cancelled the pending action.")
            yield _sse_done()
            return

        if pending.requires_auth:
            if matches_assistant_pin(msg):
                clear_pending_action(current_user, session_id)
                async for chunk in _run_tools_and_reply(
                    request, pending.tool_calls, auth_header,
                    pending.user_message, history, current_user, confirmed=True,
                    enable_thinking=config.assistant_enable_thinking,
                    already_running=set(),
                ):
                    yield chunk
                return

            if is_affirmative(msg):
                card = build_confirmation_card(pending.tool_calls, True, pin_attempts=pending.pin_attempts)
                yield _sse_gate(pending.action_id, True, card.model_dump(), _expires_in(pending.expires_at))
                yield _sse_content("Enter your PIN to continue.")
                yield _sse_done()
                return

            remaining = register_pin_rejection(pending)
            if remaining <= 0:
                clear_pending_action(current_user, session_id)
                yield _sse_content(f"Incorrect PIN. Maximum attempts ({PIN_MAX_ATTEMPTS}) reached. Cancelled.")
                yield _sse_done()
                return

            card = build_confirmation_card(pending.tool_calls, True, pin_attempts=pending.pin_attempts)
            yield _sse_gate(pending.action_id, True, card.model_dump(), _expires_in(pending.expires_at))
            yield _sse_content(f"Incorrect PIN. {remaining} attempt(s) remaining. Enter your PIN or say cancel.")
            yield _sse_done()
            return

        if is_affirmative(msg):
            clear_pending_action(current_user, session_id)
            async for chunk in _run_tools_and_reply(
                request, pending.tool_calls, auth_header,
                pending.user_message, history, current_user, confirmed=True,
                enable_thinking=config.assistant_enable_thinking,
                already_running=set(),
            ):
                yield chunk
            return

        # New unrelated message — cancel pending and continue
        cancellation_msg = cancel_pending_action_by_ai(current_user, session_id, "New request received")
        if cancellation_msg:
            history.append({"role": "assistant", "content": cancellation_msg})
        history = [h for h in history if h.get("content") != pending.user_message]
        SESSION_STORE[current_user] = history

    # ── Planning phase: stream thinking, buffer tool calls ───────────────────
    history.append({"role": "user", "content": message})
    history = trim_history(history)

    tool_calls: list[dict] = []
    thinking_on = config.assistant_enable_thinking
    streamed_during_planning = False
    planning_content_buffer: list[str] = []
    real_tool_detected = False
    detected_tools: set[str] = set()
    try:
        async for item in plan_tool_calls_streaming(message, history[:-1], enable_thinking=thinking_on):
            if isinstance(item, dict):
                if thinking_on and item["type"] == "thinking":
                    yield _sse_thinking(item["text"])
                elif item["type"] == "content":
                    if not real_tool_detected:
                        planning_content_buffer.append(item["text"])
                elif item["type"] == "tool_detected":
                    real_tool_detected = True
                    planning_content_buffer = []
                    tname = item["text"]
                    # Only show "running" status early if no confirmation is needed
                    if not requires_gate(tname):
                        yield _sse_tool(tname, "running")
                        detected_tools.add(tname)
                # planning_done is internal bookkeeping, not surfaced to client
                pass
            elif isinstance(item, list):
                tool_calls = item
    except Exception as exc:
        logger.error("Streaming planner failed: %s", exc, exc_info=True)
        yield _sse_error(str(exc))
        yield _sse_done()
        return

    # ── Conversational reply (no tools needed) ────────────────────────────────
    if len(tool_calls) == 1 and tool_calls[0].get("tool") == "none":
        if planning_content_buffer:
            for chunk in planning_content_buffer:
                yield _sse_content(chunk)
            streamed_during_planning = True
        reply_text: str = tool_calls[0].get("conversational_reply") or "Hello! How can I help you today?"
        if not streamed_during_planning:
            yield _sse_content(reply_text)
        history.append({"role": "assistant", "content": reply_text})
        SESSION_STORE[current_user] = trim_history(history)
        yield _sse_done()
        return

    # ── Gate check ────────────────────────────────────────────────────────────
    gated_calls = [
        tc for tc in tool_calls
        if tc.get("tool") and tc["tool"] != "none" and requires_gate(str(tc["tool"]))
    ]
    if gated_calls:
        require_pin = bool(config.assistant_action_pin) and any(
            requires_auth(str(tc["tool"])) for tc in gated_calls
        )
        pending = register_pending_action(current_user, session_id, message, tool_calls, requires_auth=require_pin)
        card = build_confirmation_card(tool_calls, require_pin, pin_attempts=0)
        yield _sse_gate(pending.action_id, require_pin, card.model_dump(), _expires_in(pending.expires_at))
        yield _sse_content(pending.prompt)
        yield _sse_done()
        return

    # ── Execute tools + stream reply ──────────────────────────────────────────
    async for chunk in _run_tools_and_reply(
        request, tool_calls, auth_header, message, history, current_user, confirmed=False,
        enable_thinking=config.assistant_enable_thinking,
        already_running=detected_tools,
    ):
        yield chunk



