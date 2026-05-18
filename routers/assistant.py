import asyncio
import json

import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from dependencies import get_current_user
from routers.assistant_core import (
    SESSION_STORE,
    _compose_final_reply,
    _execute_tool_safe,
    _get_or_init_session,
    _plan_tool_calls,
    _trim_history,
    config,
    logger,
)

router = APIRouter(prefix="/assistant", tags=["assistant"])


class AssistantRequest(BaseModel):
    message: str


class AssistantResponse(BaseModel):
    reply: str


@router.post("/chat", response_model=AssistantResponse, dependencies=[Depends(get_current_user)])
async def chat(
    body: AssistantRequest,
    request: Request,
    current_user: str = Depends(get_current_user),
) -> AssistantResponse:
    auth_header = request.headers.get("authorization")
    history = _get_or_init_session(current_user)

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
        tasks = [
            _execute_tool_safe(request.app, tc["tool"], tc.get("tool_input") or {}, auth_header)
            for tc in tool_calls
            if tc.get("tool") and tc["tool"] != "none"
        ]
        tool_results = list(await asyncio.gather(*tasks))

        try:
            reply_text = _compose_final_reply(body.message, tool_results)
        except Exception as exc:
            logger.error("Final response composition failed: %s", exc, exc_info=True)
            reply_text = "\n".join(
                f"- **{r['tool']}**: {r['error'] or json.dumps(r['result'], separators=(',', ':'))}"
                for r in tool_results
            )

    reply_text = reply_text.strip()
    history.append({"role": "assistant", "content": reply_text})
    SESSION_STORE[current_user] = _trim_history(history)

    return AssistantResponse(reply=reply_text)
