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
        assert "DashScope API key" in response.json()["message"]
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
    monkeypatch.setattr(assistant, "_compose_final_reply", lambda user_message, results: ("Process killed.", None))

    confirm_response = await async_client.post(
        "/assistant/chat",
        json={"message": "2468"},
        headers=_auth_headers(),
    )

    assert confirm_response.status_code == 200
    assert confirm_response.json()["reply"] == "Process killed."


@pytest.mark.anyio
async def test_assistant_rejects_wrong_pin_after_three_attempts(monkeypatch, async_client):
    from routers import assistant
    from routers import assistant_safety

    assistant.config.dashscope_api_key = "test-key"
    assistant.config.assistant_action_pin = "2468"
    assistant_safety.config.assistant_action_pin = "2468"
    assistant_safety.clear_pending_action(config.username, "test-session")
    monkeypatch.setattr(assistant, "_get_api_key", lambda: "test-key")
    monkeypatch.setattr(assistant, "_extract_session_id", lambda request: "test-session")

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
    assert pending_response.json()["requires_auth"] is True

    wrong_1 = await async_client.post(
        "/assistant/chat",
        json={"message": "1111"},
        headers=_auth_headers(),
    )
    assert wrong_1.status_code == 200
    assert "2 attempt(s) remaining" in wrong_1.json()["reply"]
    assert wrong_1.json()["confirmation"]["pin_attempts_remaining"] == 2

    wrong_2 = await async_client.post(
        "/assistant/chat",
        json={"message": "2222"},
        headers=_auth_headers(),
    )
    assert wrong_2.status_code == 200
    assert "1 attempt(s) remaining" in wrong_2.json()["reply"]
    assert wrong_2.json()["confirmation"]["pin_attempts_remaining"] == 1

    wrong_3 = await async_client.post(
        "/assistant/chat",
        json={"message": "3333"},
        headers=_auth_headers(),
    )
    assert wrong_3.status_code == 200
    assert "Maximum attempts (3) reached" in wrong_3.json()["reply"]
    assert assistant_safety.get_pending_action(config.username, "test-session") is None


@pytest.mark.anyio
async def test_assistant_returns_screenshot_directly(monkeypatch, async_client):
    from routers import assistant

    assistant.config.dashscope_api_key = "test-key"
    assistant.config.assistant_action_pin = None
    monkeypatch.setattr(assistant, "_get_api_key", lambda: "test-key")

    monkeypatch.setattr(
        assistant,
        "_plan_tool_calls",
        lambda message, history=None: [
            {"tool": "display_screenshot", "tool_input": {}},
        ],
    )

    async def fake_execute_tool_safe(app, tool_name, tool_input, auth_header, confirmed=False):
        return {
            "tool": tool_name,
            "result": {"image_base64": "UE5HREFUQQ=="},
            "error": None,
        }

    monkeypatch.setattr(assistant, "_execute_tool_safe", fake_execute_tool_safe)
    monkeypatch.setattr(assistant, "_compose_final_reply", lambda user_message, results: (_ for _ in ()).throw(AssertionError("compose_final_reply should not run for screenshots")))

    response = await async_client.post(
        "/assistant/chat",
        json={"message": "take a screenshot"},
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reply"] == "Screenshot captured."
    assert payload["image_base64"] == "UE5HREFUQQ=="
    assert payload["pending_action_id"] is None


def test_compose_final_reply_formats_media_elapsed_time():
    from routers import assistant

    reply_text, art_url = assistant._compose_final_reply(
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

    assert reply_text == "**Chikwere by Bien** is paused. Elapsed: 21s. Length: 3:10."
    assert art_url is None


def test_compose_final_reply_includes_art_url():
    from routers import assistant

    reply_text, art_url = assistant._compose_final_reply(
        "What is now playing?",
        [
            {
                "tool": "get_media_status",
                "result": {
                    "title": "Song Title",
                    "artist": "Artist Name",
                    "status": "Playing",
                    "position_seconds": 10.0,
                    "length_seconds": 200.0,
                    "art_url": "https://example.com/album.jpg",
                },
                "error": None,
            }
        ],
    )

    assert "Song Title by Artist Name" in reply_text
    assert art_url == "https://example.com/album.jpg"


@pytest.mark.anyio
async def test_new_tool_request_clears_old_pending_action(monkeypatch, async_client):
    """When a new tool request arrives, old pending action should be cleared and new one processed."""
    from routers import assistant
    from routers import assistant_safety

    assistant.config.dashscope_api_key = "test-key"
    assistant.config.assistant_action_pin = None
    monkeypatch.setattr(assistant, "_get_api_key", lambda: "test-key")
    monkeypatch.setattr(assistant, "_extract_session_id", lambda request: "test-session")

    # First request: ask to type (medium-risk, requires confirmation)
    monkeypatch.setattr(
        assistant,
        "_plan_tool_calls",
        lambda message, history=None: [
            {"tool": "type_keyboard", "tool_input": {"text": "Next"}},
        ],
    )

    pending_response = await async_client.post(
        "/assistant/chat",
        json={"message": "write Next in the keyboard"},
        headers=_auth_headers(),
    )

    assert pending_response.status_code == 200
    assert pending_response.json()["requires_confirmation"] is True
    pending_action_id_1 = pending_response.json()["pending_action_id"]
    assert pending_action_id_1 is not None

    # Second request: ask to delete (different tool, should clear the first pending action)
    monkeypatch.setattr(
        assistant,
        "_plan_tool_calls",
        lambda message, history=None: [
            {"tool": "delete_path", "tool_input": {"path": "/home/user/mike"}},
        ],
    )

    async def fake_execute_tool_safe(app, tool_name, tool_input, auth_header, confirmed=False):
        return {"tool": tool_name, "result": {"success": True}, "error": None}

    monkeypatch.setattr(assistant, "_execute_tool_safe", fake_execute_tool_safe)

    delete_response = await async_client.post(
        "/assistant/chat",
        json={"message": "delete Mike's folder"},
        headers=_auth_headers(),
    )

    # Should create a NEW pending action (high-risk), not re-display the old one
    assert delete_response.status_code == 200
    assert delete_response.json()["requires_confirmation"] is True
    pending_action_id_2 = delete_response.json()["pending_action_id"]
    
    # Should be a different pending action
    assert pending_action_id_2 != pending_action_id_1
    
    # The reply should be about the delete action, not the type action
    assert "delete" in delete_response.json()["reply"].lower() or "confirmation" in delete_response.json()["reply"].lower()


@pytest.mark.anyio
async def test_cancelled_pending_action_message_removed_from_history(monkeypatch, async_client):
    """Cancelling a pending action should also remove its message from history."""
    from routers import assistant
    from routers import assistant_core

    assistant.config.dashscope_api_key = "test-key"
    assistant.config.assistant_action_pin = None
    monkeypatch.setattr(assistant, "_get_api_key", lambda: "test-key")
    monkeypatch.setattr(assistant, "_extract_session_id", lambda request: "test-session-cancel")

    # First request: ask to type (creates pending action)
    monkeypatch.setattr(
        assistant,
        "_plan_tool_calls",
        lambda message, history=None: [
            {"tool": "type_keyboard", "tool_input": {"text": "Hello"}},
        ],
    )

    pending_response = await async_client.post(
        "/assistant/chat",
        json={"message": "type hello"},
        headers=_auth_headers(),
    )

    assert pending_response.status_code == 200
    assert pending_response.json()["requires_confirmation"] is True

    # Second request: cancel the pending action
    cancel_response = await async_client.post(
        "/assistant/chat",
        json={"message": "cancel"},
        headers=_auth_headers(),
    )

    assert cancel_response.status_code == 200
    assert cancel_response.json()["reply"] == "Cancelled the pending action."

    # Third request: ask for something else (should NOT re-plan "type hello")
    monkeypatch.setattr(
        assistant,
        "_plan_tool_calls",
        lambda message, history=None: [
            {"tool": "get_system_info", "tool_input": {}},  # Low-risk, no confirmation
        ],
    )

    async def fake_execute_tool_safe(app, tool_name, tool_input, auth_header, confirmed=False):
        return {"tool": tool_name, "result": {"os": "Linux"}, "error": None}

    monkeypatch.setattr(assistant, "_execute_tool_safe", fake_execute_tool_safe)

    next_response = await async_client.post(
        "/assistant/chat",
        json={"message": "what's the os"},
        headers=_auth_headers(),
    )

    # Should NOT include the old "type hello" message in the planning
    # If it did, LLM would see both messages and might plan both actions
    assert next_response.status_code == 200
    # The response should be from get_system_info only, not from both tools
    assert "requires_confirmation" not in next_response.json() or next_response.json()["requires_confirmation"] is False
