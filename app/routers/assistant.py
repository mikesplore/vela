import asyncio
import hashlib
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.dependencies import get_current_user
from .assistant_core import (
    SESSION_STORE,
    _compose_final_reply,
    _execute_tool_safe,
    _get_or_init_session,
    _get_api_key,
    _plan_tool_calls,
    _trim_history,
    config,
    logger,
)
from .assistant_safety import (
    ConfirmationCard,
    PIN_MAX_ATTEMPTS,
    PendingAction,
    build_confirmation_card,
    clear_pending_action,
    get_pending_action,
    is_affirmative,
    is_negative,
    matches_assistant_pin,
    register_pin_rejection,
    register_pending_action,
    requires_auth,
    requires_gate,
)

router = APIRouter(prefix="/assistant", tags=["assistant"])


def _extract_session_id(request: Request) -> str:
    """Extract a persistent session ID from request headers.

    Each client/app should generate a unique session ID (any string) once,
    store it persistently, and include it in every request via X-Session-ID header.
    This ensures multi-step confirmations (pending actions) work correctly.

    Session IDs must be consistent across multiple requests from the same device/client.
    """
    session_id = request.headers.get("X-Session-ID")
    if session_id:
        return session_id

    # Fallback: try relay-provided device ID
    device_id = request.headers.get("X-Forwarded-Device-Id") or request.headers.get("X-Device-Id")
    if device_id:
        return device_id

    # Last resort: hash User-Agent + X-Forwarded-For (for relay) or direct IP
    user_agent = request.headers.get("User-Agent", "unknown")
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"

    combined = f"{user_agent}|{client_ip}"
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


class AssistantRequest(BaseModel):
    message: str


class AssistantResponse(BaseModel):
    reply: str
    image_base64: str | None = None
    art_url: str | None = None
    pending_action_id: str | None = None
    requires_confirmation: bool = False
    requires_auth: bool = False
    expires_in_seconds: int | None = None
    confirmation: ConfirmationCard | None = None


def _pending_response(pending: PendingAction) -> AssistantResponse:
    expires_in_seconds = max(0, int((pending.expires_at - datetime.now(pending.expires_at.tzinfo)).total_seconds()))
    confirmation_card = build_confirmation_card(
        pending.tool_calls,
        pending.requires_auth,
        pin_attempts=pending.pin_attempts,
    )
    return AssistantResponse(
        reply=pending.prompt,
        pending_action_id=pending.action_id,
        requires_confirmation=True,
        requires_auth=pending.requires_auth,
        expires_in_seconds=expires_in_seconds,
        confirmation=confirmation_card,
    )


async def _execute_tool_calls(request: Request, tool_calls: list[dict[str, object]], auth_header: str | None,
                              user_message: str = "", confirmed: bool = False) -> AssistantResponse:
    tasks = [
        _execute_tool_safe(request.app, tc["tool"], tc.get("tool_input") or {}, auth_header, confirmed=confirmed)
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
        reply_text, art_url = _compose_final_reply(user_message, tool_results)
    except Exception as exc:
        logger.error("Final response composition failed: %s", exc, exc_info=True)
        reply_text = "\n".join(
            f"- **{r['tool']}**: {r['error'] or json.dumps(r['result'], separators=(',', ':'))}"
            for r in tool_results
        )
        art_url = None
    return AssistantResponse(reply=reply_text, art_url=art_url)


@router.post("/chat", response_model=AssistantResponse, dependencies=[Depends(get_current_user)])
async def chat(
        body: AssistantRequest,
        request: Request,
        current_user: str = Depends(get_current_user),
) -> AssistantResponse:
    if not _get_api_key():
        raise HTTPException(status_code=503, detail="FIREWORKS_API_KEY is unavailable")

    session_id = _extract_session_id(request)
    auth_header = request.headers.get("authorization")
    history = _get_or_init_session(current_user)

    pending = get_pending_action(current_user, session_id)

    if pending:
        message = body.message.strip()
        if is_negative(message):
            clear_pending_action(current_user, session_id)
            # Remove the original message that triggered this pending action from history
            # so it doesn't get re-planned on the next request
            history = _get_or_init_session(current_user)
            history = [h for h in history if h.get("content") != pending.user_message]
            SESSION_STORE[current_user] = history
            return AssistantResponse(reply="Cancelled the pending action.")
        if pending.requires_auth:
            if matches_assistant_pin(message):
                clear_pending_action(current_user, session_id)
                tool_response = await _execute_tool_calls(request, pending.tool_calls, auth_header,
                                                          user_message=pending.user_message, confirmed=True)
                history.append({"role": "assistant", "content": tool_response.reply})
                SESSION_STORE[current_user] = _trim_history(history)
                return tool_response
            if is_affirmative(message):
                confirmation_card = build_confirmation_card(
                    pending.tool_calls,
                    pending.requires_auth,
                    pin_attempts=pending.pin_attempts,
                )
                return AssistantResponse(
                    reply="Enter your PIN to continue.",
                    pending_action_id=pending.action_id,
                    requires_confirmation=True,
                    requires_auth=True,
                    expires_in_seconds=max(0, int((pending.expires_at - datetime.now(timezone.utc)).total_seconds())),
                    confirmation=confirmation_card,
                )

            remaining_attempts = register_pin_rejection(pending)
            if remaining_attempts <= 0:
                clear_pending_action(current_user, session_id)
                return AssistantResponse(
                    reply=f"Incorrect PIN. Maximum attempts ({PIN_MAX_ATTEMPTS}) reached. Cancelled the pending action.",
                )

            confirmation_card = build_confirmation_card(
                pending.tool_calls,
                pending.requires_auth,
                pin_attempts=pending.pin_attempts,
            )
            return AssistantResponse(
                reply=f"Incorrect PIN. {remaining_attempts} attempt(s) remaining. Enter your PIN to continue or say cancel.",
                pending_action_id=pending.action_id,
                requires_confirmation=True,
                requires_auth=True,
                expires_in_seconds=max(0, int((pending.expires_at - datetime.now(timezone.utc)).total_seconds())),
                confirmation=confirmation_card,
            )
        if is_affirmative(message):
            clear_pending_action(current_user, session_id)
            tool_response = await _execute_tool_calls(request, pending.tool_calls, auth_header,
                                                      user_message=pending.user_message, confirmed=True)
            history.append({"role": "assistant", "content": tool_response.reply})
            SESSION_STORE[current_user] = _trim_history(history)
            return tool_response

        # New request: clear the old pending action and remove its message from history
        clear_pending_action(current_user, session_id)
        history = [h for h in history if h.get("content") != pending.user_message]
        SESSION_STORE[current_user] = history

    history.append({"role": "user", "content": body.message})
    history = _trim_history(history)

    try:
        tool_calls = _plan_tool_calls(body.message, history[:-1])
    except Exception as exc:
        logger.error("Tool planning failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail=str(exc))

    if len(tool_calls) == 1 and tool_calls[0].get("tool") == "none":
        reply_text: str = tool_calls[0].get("conversational_reply") or "Hello! How can I help you today?"
    else:
        gated_calls = [tc for tc in tool_calls if
                       tc.get("tool") and tc["tool"] != "none" and requires_gate(str(tc["tool"]))]
        if gated_calls:
            require_pin = bool(config.assistant_action_pin) and any(
                requires_auth(str(tc["tool"])) for tc in gated_calls)
            pending = register_pending_action(current_user, session_id, body.message, tool_calls,
                                              requires_auth=require_pin)
            reply_text = pending.prompt
            confirmation_card = build_confirmation_card(
                pending.tool_calls,
                pending.requires_auth,
                pin_attempts=pending.pin_attempts,
            )
            return AssistantResponse(
                reply=reply_text,
                pending_action_id=pending.action_id,
                requires_confirmation=True,
                requires_auth=pending.requires_auth,
                expires_in_seconds=max(0, int((pending.expires_at - datetime.now(timezone.utc)).total_seconds())),
                confirmation=confirmation_card,
            )

        tool_response = await _execute_tool_calls(request, tool_calls, auth_header, user_message=body.message,
                                                  confirmed=False)
        tool_response.reply = tool_response.reply.strip()
        history.append({"role": "assistant", "content": tool_response.reply})
        SESSION_STORE[current_user] = _trim_history(history)
        return tool_response

    reply_text = reply_text.strip()
    history.append({"role": "assistant", "content": reply_text})
    SESSION_STORE[current_user] = _trim_history(history)

    return AssistantResponse(reply=reply_text)