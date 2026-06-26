import asyncio
import json
from datetime import datetime, UTC

from fastapi import APIRouter, HTTPException, Request

from app.domain.assistant import AssistantResponse
from app.services.assistant.core import (
    compose_final_reply,
    execute_tool_safe,
    logger, )
from app.services.assistant.safety import (
    PendingAction,
    build_confirmation_card,
)



router = APIRouter(prefix="/assistant", tags=["assistant"])


def extract_session_id(request: Request) -> str:
    """Extract a persistent session ID from request headers.

    Each client/app should generate a unique session ID (any string) once,
    store it persistently, and include it in every request via X-Session-ID header.
    This ensures multi-step confirmations (pending actions) work correctly.

    Session IDs must be consistent across multiple requests from the same device/client.
    """
    session_id = extract_session_id(request)
    if not session_id:
        raise HTTPException(status_code=400, detail="X-Session-ID header is required")
    return session_id


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


async def execute_tool_calls(request: Request, tool_calls: list[dict[str, object]], auth_header: str | None,
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
