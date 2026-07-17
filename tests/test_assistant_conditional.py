import pytest

from app.auth import create_access_token
from app.services.assistant import tool_exec


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {create_access_token({'sub': 'admin'})}",
        "X-Session-ID": "conditional-test-session",
    }


@pytest.mark.anyio
async def test_conditional_request_inspects_then_executes_matching_branch(monkeypatch, async_client):
    from app.routers import assistant as assistant_router
    from app.services.assistant import helpers

    planned: list[str] = []
    executed: list[str] = []
    monkeypatch.setattr(assistant_router, "get_api_key", lambda: "test-key")

    async def first_plan(*_args, **_kwargs):
        planned.append("inspection")
        return [
            {"tool": "get_currently_playing_song", "tool_input": {}},
            {"tool": "get_battery", "tool_input": {}},
        ]

    async def followup_plan(*_args, **_kwargs):
        planned.append("action")
        return [{"tool": "mute_audio", "tool_input": {"muted": True}}]

    async def fake_execute(app, tool_name, tool_input, auth_header, confirmed=False):
        executed.append(tool_name)
        results = {
            "get_currently_playing_song": {"status": "playing", "title": "Test track"},
            "get_battery": {"status": "charging"},
            "mute_audio": {"success": True},
        }
        return {"tool": tool_name, "result": results[tool_name], "error": None}

    async def fake_reply(_message, results):
        return f"Executed: {', '.join(item['tool'] for item in results)}", None

    monkeypatch.setattr(assistant_router, "plan_tool_calls", first_plan)
    monkeypatch.setattr(assistant_router, "plan_conditional_followup", followup_plan)
    monkeypatch.setattr(tool_exec, "execute_tool_safe", fake_execute)
    monkeypatch.setattr(helpers, "compose_final_reply", fake_reply)

    response = await async_client.post(
        "/assistant/chat",
        json={"message": "If music is playing mute it, otherwise set volume to 60."},
        headers=_headers(),
    )

    assert response.status_code == 200
    assert planned == ["inspection", "action"]
    assert executed == ["get_currently_playing_song", "get_battery", "mute_audio"]
    assert "mute_audio" in response.json()["reply"]


@pytest.mark.anyio
async def test_conditional_followup_action_still_requires_confirmation(monkeypatch, async_client):
    from app.routers import assistant as assistant_router

    monkeypatch.setattr(assistant_router, "get_api_key", lambda: "test-key")

    async def first_plan(*_args, **_kwargs):
        return [{"tool": "get_battery", "tool_input": {}}]

    async def followup_plan(*_args, **_kwargs):
        return [{"tool": "close_application", "tool_input": {"name": "chrome"}}]

    async def fake_execute(app, tool_name, tool_input, auth_header, confirmed=False):
        return {"tool": tool_name, "result": {"status": "charging"}, "error": None}

    monkeypatch.setattr(assistant_router, "plan_tool_calls", first_plan)
    monkeypatch.setattr(assistant_router, "plan_conditional_followup", followup_plan)
    monkeypatch.setattr(tool_exec, "execute_tool_safe", fake_execute)

    response = await async_client.post(
        "/assistant/chat",
        json={"message": "If my battery is charging, close Chrome."},
        headers=_headers(),
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["requires_confirmation"] is True
    assert payload["confirmation"]["action_type"] == "close_application"
