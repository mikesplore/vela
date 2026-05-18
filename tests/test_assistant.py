import pytest

from auth import create_access_token
from config import Config

config = Config()


def _auth_headers() -> dict[str, str]:
    token = create_access_token(data={"sub": config.username})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_assistant_chat_requires_api_key(async_client):
    from routers import assistant

    assistant.config.dashscope_api_key = None
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(assistant, "_get_api_key", lambda: None)

    try:
        response = await async_client.post(
            "/assistant/chat",
            json={"message": "Hello"},
            headers=_auth_headers(),
        )
        assert response.status_code == 503
        assert "DashScope API key" in response.json()["detail"]
    finally:
        monkeypatch.undo()


@pytest.mark.anyio
async def test_assistant_chat_returns_reply(monkeypatch, async_client):
    from routers import assistant

    assistant.config.dashscope_api_key = "test-key"
    assistant.config.dashscope_api_url = "https://api.test/v1/chat/completions"
    assistant.config.assistant_action_pin = None
    monkeypatch.setattr(assistant, "_get_api_key", lambda: "test-key")

    monkeypatch.setattr(
        assistant,
        "_plan_tool_calls",
        lambda message, history=None: [{"tool": "none", "tool_input": {}, "conversational_reply": "Test reply"}],
    )

    response = await async_client.post(
        "/assistant/chat",
        json={"message": "What is the status?"},
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    assert response.json()["reply"] == "Test reply"


@pytest.mark.anyio
async def test_assistant_requires_pin_for_high_risk_action(monkeypatch, async_client):
    from routers import assistant
    from routers import assistant_safety

    assistant.config.dashscope_api_key = "test-key"
    assistant.config.assistant_action_pin = "2468"
    assistant_safety.config.assistant_action_pin = "2468"
    monkeypatch.setattr(assistant, "_get_api_key", lambda: "test-key")

    monkeypatch.setattr(
        assistant,
        "_plan_tool_calls",
        lambda message, history=None: [
            {"tool": "kill_process", "tool_input": {"pid": 1234}},
        ],
    )

    pending_response = await async_client.post(
        "/assistant/chat",
        json={"message": "kill it"},
        headers=_auth_headers(),
    )

    assert pending_response.status_code == 200
    pending_payload = pending_response.json()
    assert pending_payload["requires_auth"] is True
    assert pending_payload["pending_action_id"] is not None
    assert "PIN" in pending_payload["reply"]

    async def fake_execute_tool_safe(app, tool_name, tool_input, auth_header, confirmed=False):
        return {"tool": tool_name, "result": {"success": True, "message": "done"}, "error": None}

    monkeypatch.setattr(assistant, "_execute_tool_safe", fake_execute_tool_safe)
    monkeypatch.setattr(assistant, "_compose_final_reply", lambda user_message, results: "Process killed.")

    confirm_response = await async_client.post(
        "/assistant/chat",
        json={"message": "2468"},
        headers=_auth_headers(),
    )

    assert confirm_response.status_code == 200
    assert confirm_response.json()["reply"] == "Process killed."


def test_compose_final_reply_formats_media_elapsed_time():
    from routers import assistant

    reply = assistant._compose_final_reply(
        "What is the elapsed time of the current music?",
        [
            {
                "tool": "get_media_status",
                "result": {
                    "title": "Chikwere",
                    "artist": "Bien",
                    "status": "Paused",
                    "position_seconds": 21.248,
                    "length_seconds": 189.6,
                },
                "error": None,
            }
        ],
    )

    assert reply == "**Chikwere by Bien** is paused. Elapsed: 21s. Length: 3:10."
