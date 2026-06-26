import asyncio
import json
from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException, Request

from app.dependencies import get_current_user
from domain.assistant import AssistantResponse, AssistantRequest
from app.services.assistant.core import (
    SESSION_STORE,
    compose_final_reply,
    execute_tool_safe,
    config,
    logger, get_api_key, get_or_init_session, trim_history, plan_tool_calls,
)
from app.services.assistant.safety import (
    PIN_MAX_ATTEMPTS,
    PendingAction,
    build_confirmation_card,
    cancel_pending_action_by_ai,
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
    session_id = _extract_session_id(request)
    if not session_id:
        raise HTTPException(status_code=400, detail="X-Session-ID header is required")
    return session_id



def _expires_in_seconds(expires_at: datetime) -> int:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return max(0, int((expires_at - datetime.now(UTC)).total_seconds()))


def _pending_response(pending: PendingAction) -> AssistantResponse:
    expires_in_seconds = _expires_in_seconds(pending.expires_at)
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


async def _execute_tool_calls(request: Request, tool_calls: list[dict[str, object]], auth_header: str | None,
                              user_message: str = "", confirmed: bool = False) -> AssistantResponse:
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


@router.post("/chat", response_model=AssistantResponse, dependencies=[Depends(get_current_user)])
async def chat(
        body: AssistantRequest,
        request: Request,
        current_user: str = Depends(get_current_user),
) -> AssistantResponse:
    if not get_api_key():
        raise HTTPException(status_code=503, detail="FIREWORKS_API_KEY is unavailable")

    session_id = _extract_session_id(request)
    auth_header = request.headers.get("authorization")
    history = get_or_init_session(current_user)

    pending = get_pending_action(current_user, session_id)

    if pending:
        message = body.message.strip()
        if is_negative(message):
            clear_pending_action(current_user, session_id)
            # Remove the original message that triggered this pending action from history
            # so it doesn't get re-planned on the next request
            history = get_or_init_session(current_user)
            history = [h for h in history if h.get("content") != pending.user_message]
            SESSION_STORE[current_user] = history
            return AssistantResponse(reply="Cancelled the pending action.")
        if pending.requires_auth:
            if matches_assistant_pin(message):
                clear_pending_action(current_user, session_id)
                tool_response = await _execute_tool_calls(request, pending.tool_calls, auth_header,
                                                          user_message=pending.user_message, confirmed=True)
                history.append({"role": "assistant", "content": tool_response.reply})
                SESSION_STORE[current_user] = trim_history(history)
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
                    requires_confirmation=False,
                    requires_auth=True,
                    expires_in_seconds=_expires_in_seconds(pending.expires_at),
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
                requires_confirmation=False,
                requires_auth=True,
                expires_in_seconds=_expires_in_seconds(pending.expires_at),
                confirmation=confirmation_card,
            )
        if is_affirmative(message):
            clear_pending_action(current_user, session_id)
            tool_response = await _execute_tool_calls(request, pending.tool_calls, auth_header,
                                                      user_message=pending.user_message, confirmed=True)
            history.append({"role": "assistant", "content": tool_response.reply})
            SESSION_STORE[current_user] = trim_history(history)
            return tool_response

        # AI-initiated cancellation: new request overrides the pending action
        cancellation_msg = cancel_pending_action_by_ai(current_user, session_id, "New request received")
        if cancellation_msg:
            history.append({"role": "assistant", "content": cancellation_msg})
        history = [h for h in history if h.get("content") != pending.user_message]
        SESSION_STORE[current_user] = history

    history.append({"role": "user", "content": body.message})
    history = trim_history(history)

    try:
        tool_calls = await plan_tool_calls(body.message, history[:-1])
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
                requires_confirmation=not pending.requires_auth,
                requires_auth=pending.requires_auth,
                expires_in_seconds=_expires_in_seconds(pending.expires_at),
                confirmation=confirmation_card,
            )

        tool_response = await _execute_tool_calls(request, tool_calls, auth_header, user_message=body.message,
                                                  confirmed=False)
        tool_response.reply = tool_response.reply.strip()
        history.append({"role": "assistant", "content": tool_response.reply})
        SESSION_STORE[current_user] = trim_history(history)
        return tool_response

    reply_text = reply_text.strip()
    history.append({"role": "assistant", "content": reply_text})
    SESSION_STORE[current_user] = trim_history(history)

    return AssistantResponse(reply=reply_text)