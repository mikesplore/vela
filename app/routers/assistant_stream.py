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
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.dependencies import get_current_user
from .assistant_core import (
    SESSION_STORE,
    _execute_tool_safe,
    _get_api_key,
    _get_or_init_session,
    _plan_tool_calls_streaming,
    _stream_llm_response,
    _trim_history,
    _compose_final_reply,
    config,
    logger,
)
from .assistant_safety import (
    PIN_MAX_ATTEMPTS,
    build_confirmation_card,
    build_pending_prompt,
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

def _sse_tool(name: str, status: str, result: dict | None = None, error: str | None = None) -> str:
    payload: dict = {"name": name, "status": status}
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
) -> AsyncGenerator[str, None]:
    real_calls = [tc for tc in tool_calls if tc.get("tool") and tc["tool"] != "none"]

    for tc in real_calls:
        yield _sse_tool(tc["tool"], "running")

    tasks = [
        _execute_tool_safe(
            request.app, tc["tool"], tc.get("tool_input") or {},
            auth_header, confirmed=confirmed,
        )
        for tc in real_calls
    ]
    tool_results = list(await asyncio.gather(*tasks))

    for r in tool_results:
        if r.get("error"):
            yield _sse_tool(r["tool"], "error", error=r["error"])
        elif r["tool"] == "display_screenshot":
            result = r.get("result") or {}
            img = result.get("image_base64") if isinstance(result, dict) else None
            yield _sse("screenshot", {"image_base64": img})
            yield _sse_done()
            return
        else:
            yield _sse_tool(r["tool"], "done", result=r.get("result"))

    # Fast-path: media status (no second LLM call needed)
    if len(tool_results) == 1 and tool_results[0].get("tool") == "get_media_status":
        try:
            reply_text, art_url = await _compose_final_reply(user_message, tool_results)
        except Exception as exc:
            reply_text, art_url = str(exc), None
        if art_url:
            yield _sse("art", {"url": art_url})
        yield _sse_content(reply_text)
        history.append({"role": "assistant", "content": reply_text.strip()})
        SESSION_STORE[current_user] = _trim_history(history)
        yield _sse_done()
        return

    # Stream the final reply
    results_text = "\n".join(
        f"Tool: {r['tool']}\nResult: {json.dumps(r['result'], separators=(',', ':'))}"
        + (f"\nError: {r['error']}" if r.get("error") else "")
        for r in tool_results
    )
    reply_messages = [
        {"role": "system", "content": config.assistant_system_prompt},
        {"role": "user", "content": f"User request: {user_message}\n\n{results_text}\n\nAnswer in clean Markdown."},
    ]

    full_reply = ""
    async for delta in _stream_llm_response(reply_messages, max_tokens=1024, enable_thinking=True):
        if delta["type"] == "thinking":
            yield _sse_thinking(delta["text"])
        elif delta["type"] == "content":
            full_reply += delta["text"]
            yield _sse_content(delta["text"])
        elif delta["type"] == "error":
            yield _sse_error(delta["text"])
            yield _sse_done()
            return

    history.append({"role": "assistant", "content": full_reply.strip()})
    SESSION_STORE[current_user] = _trim_history(history)
    yield _sse_done()


# ── Main stream generator ─────────────────────────────────────────────────────

async def _stream_chat(request: Request, message: str, current_user: str) -> AsyncGenerator[str, None]:
    if not _get_api_key():
        yield _sse_error("FIREWORKS_API_KEY is unavailable.")
        yield _sse_done()
        return

    session_id = _extract_session_id(request)
    auth_header = request.headers.get("authorization")
    history = _get_or_init_session(current_user)
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
    history = _trim_history(history)

    tool_calls: list[dict] = []
    try:
        async for item in _plan_tool_calls_streaming(message, history[:-1]):
            if isinstance(item, dict):
                if item["type"] == "thinking":
                    yield _sse_thinking(item["text"])
                # planning_done is internal bookkeeping, not surfaced to client
            elif isinstance(item, list):
                tool_calls = item
    except Exception as exc:
        logger.error("Streaming planner failed: %s", exc, exc_info=True)
        yield _sse_error(str(exc))
        yield _sse_done()
        return

    # ── Conversational reply (no tools needed) ────────────────────────────────
    if len(tool_calls) == 1 and tool_calls[0].get("tool") == "none":
        reply_text: str = tool_calls[0].get("conversational_reply") or "Hello! How can I help you today?"
        yield _sse_content(reply_text)
        history.append({"role": "assistant", "content": reply_text})
        SESSION_STORE[current_user] = _trim_history(history)
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
    ):
        yield chunk


# ── Route — POST, same shape as /chat ────────────────────────────────────────

@router.post("/stream", dependencies=[Depends(get_current_user)])
async def stream_chat(
        body: StreamRequest,
        request: Request,
        current_user: str = Depends(get_current_user),
) -> StreamingResponse:
    """
    Streaming version of /assistant/chat. Returns SSE instead of JSON.

    curl -N -s -X POST https://host/assistant/stream \\
      -H "X-Secret: ..." \\
      -H "Content-Type: application/json" \\
      -H "X-Session-ID: my-client-002" \\
      -d '{"message": "max out the volume"}'
    """
    return StreamingResponse(
        _stream_chat(request, body.message, current_user),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # prevent nginx from buffering SSE
            "Connection": "keep-alive",
        },
    )