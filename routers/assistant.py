import asyncio
import json
from datetime import datetime, timezone

import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from dependencies import get_current_user
from routers.assistant_core import (
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
from routers.assistant_safety import (
    PendingAction,
    clear_pending_action,
    get_pending_action,
    is_affirmative,
    is_negative,
    matches_assistant_pin,
    register_pending_action,
    requires_auth,
    requires_gate,
)

router = APIRouter(prefix="/assistant", tags=["assistant"])


class AssistantRequest(BaseModel):
    message: str


class AssistantResponse(BaseModel):
    reply: str
    pending_action_id: str | None = None
    requires_confirmation: bool = False
    requires_auth: bool = False
    expires_in_seconds: int | None = None


def _pending_response(pending: PendingAction) -> AssistantResponse:
    expires_in_seconds = max(0, int((pending.expires_at - datetime.now(pending.expires_at.tzinfo)).total_seconds()))
    return AssistantResponse(
        reply=pending.prompt,
        pending_action_id=pending.action_id,
        requires_confirmation=True,
        requires_auth=pending.requires_auth,
        expires_in_seconds=expires_in_seconds,
    )


async def _execute_tool_calls(request: Request, tool_calls: list[dict[str, object]], auth_header: str | None, confirmed: bool = False) -> str:
    tasks = [
        _execute_tool_safe(request.app, tc["tool"], tc.get("tool_input") or {}, auth_header, confirmed=confirmed)
        for tc in tool_calls
        if tc.get("tool") and tc["tool"] != "none"
    ]
    tool_results = list(await asyncio.gather(*tasks))

    try:
        return _compose_final_reply("", tool_results)
    except Exception as exc:
        logger.error("Final response composition failed: %s", exc, exc_info=True)
        return "\n".join(
            f"- **{r['tool']}**: {r['error'] or json.dumps(r['result'], separators=(',', ':'))}"
            for r in tool_results
        )


@router.post("/chat", response_model=AssistantResponse, dependencies=[Depends(get_current_user)])
async def chat(
    body: AssistantRequest,
    request: Request,
    current_user: str = Depends(get_current_user),
) -> AssistantResponse:
    if not _get_api_key():
        raise HTTPException(status_code=503, detail="DashScope API key is unavailable")

    auth_header = request.headers.get("authorization")
    history = _get_or_init_session(current_user)

    pending = get_pending_action(current_user)
    if pending:
        message = body.message.strip()
        if is_negative(message):
            clear_pending_action(current_user)
            return AssistantResponse(reply="Cancelled the pending action.")
        if pending.requires_auth:
            if matches_assistant_pin(message):
                clear_pending_action(current_user)
                reply_text = await _execute_tool_calls(request, pending.tool_calls, auth_header, confirmed=True)
                history.append({"role": "assistant", "content": reply_text})
                SESSION_STORE[current_user] = _trim_history(history)
                return AssistantResponse(reply=reply_text)
            if is_affirmative(message):
                return AssistantResponse(
                    reply="Enter your PIN to continue.",
                    pending_action_id=pending.action_id,
                    requires_confirmation=True,
                    requires_auth=True,
                    expires_in_seconds=max(0, int((pending.expires_at - datetime.now(timezone.utc)).total_seconds())),
                )
            return _pending_response(pending)
        if is_affirmative(message):
            clear_pending_action(current_user)
            reply_text = await _execute_tool_calls(request, pending.tool_calls, auth_header, confirmed=True)
            history.append({"role": "assistant", "content": reply_text})
            SESSION_STORE[current_user] = _trim_history(history)
            return AssistantResponse(reply=reply_text)
        return _pending_response(pending)

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
        gated_calls = [tc for tc in tool_calls if tc.get("tool") and tc["tool"] != "none" and requires_gate(str(tc["tool"]))]
        if gated_calls:
            require_pin = bool(config.assistant_action_pin) and any(requires_auth(str(tc["tool"])) for tc in gated_calls)
            pending = register_pending_action(current_user, body.message, tool_calls, requires_auth=require_pin)
            reply_text = pending.prompt
            return AssistantResponse(
                reply=reply_text,
                pending_action_id=pending.action_id,
                requires_confirmation=True,
                requires_auth=pending.requires_auth,
                expires_in_seconds=max(0, int((pending.expires_at - datetime.now(timezone.utc)).total_seconds())),
            )

        reply_text = await _execute_tool_calls(request, tool_calls, auth_header, confirmed=False)

    reply_text = reply_text.strip()
    history.append({"role": "assistant", "content": reply_text})
    SESSION_STORE[current_user] = _trim_history(history)

    return AssistantResponse(reply=reply_text)
