from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from auth import create_access_token
from config import Config

config = Config()


def _auth_headers() -> dict[str, str]:
    token = create_access_token(data={"sub": config.username})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_assistant_chat_requires_api_key(async_client):
    response = await async_client.post(
        "/assistant/chat",
        json={"message": "Hello"},
        headers=_auth_headers(),
    )
    assert response.status_code == 503
    assert "DashScope API key" in response.json()["detail"]


@patch("routers.assistant.requests.post")
@pytest.mark.anyio
async def test_assistant_chat_returns_reply(mock_post, async_client):
    from routers import assistant

    assistant.config.dashscope_api_key = "test-key"
    assistant.config.dashscope_api_url = "https://api.test/v1/chat/completions"

    mock_response = mock_post.return_value
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"choices": [{"message": {"content": "Test reply"}}]}

    response = await async_client.post(
        "/assistant/chat",
        json={"message": "What is the status?"},
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    assert response.json()["reply"] == "Test reply"


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
