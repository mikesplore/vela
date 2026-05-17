from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from auth import create_access_token
from config import Config

config = Config()


def _auth_headers() -> dict[str, str]:
    token = create_access_token(data={"sub": config.username})
    return {"Authorization": f"Bearer {token}"}


async def test_assistant_chat_requires_api_key(async_client):
    response = await async_client.post(
        "/assistant/chat",
        json={"message": "Hello"},
        headers=_auth_headers(),
    )
    assert response.status_code == 503
    assert "DashScope API key" in response.json()["detail"]


@patch("routers.assistant.requests.post")
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
