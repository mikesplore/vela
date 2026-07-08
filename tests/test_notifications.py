import pytest

from app.auth import create_access_token
from app.routers import notifications as notifications_module


@pytest.mark.anyio
async def test_notifications_send_read_clear(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    def fakerun_command(cmd, timeout=10):
        return "", "", 0

    monkeypatch.setattr(notifications_module, "run_command", fakerun_command)

    response = await async_client.post(
        "/notifications/send",
        json={"title": "Hello", "message": "World", "app_name": "Vela", "urgency": "normal"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Hello"
    assert payload["message"] == "World"

    read_response = await async_client.get(
        "/notifications/read",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert read_response.status_code == 200
    notifications = read_response.json()["notifications"]
    assert len(notifications) == 1
    assert notifications[0]["title"] == "Hello"

    clear_response = await async_client.post(
        "/notifications/clear",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert clear_response.status_code == 200
    assert clear_response.json()["success"] is True

    read_after_clear = await async_client.get(
        "/notifications/read",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert read_after_clear.json()["notifications"] == []

    # The /notifications/list endpoint may return actual desktop notification history if available.
    list_response = await async_client.get(
        "/notifications/list",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_response.status_code == 200
    assert list_response.json()["notifications"] == []
