import pytest
from auth import create_access_token
from routers import input_control as input_control_module


@pytest.mark.anyio
async def test_input_control_requires_confirmation_header(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    response = await async_client.post(
        "/input/mouse/move",
        json={"x": 100, "y": 100},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


@pytest.mark.anyio
async def test_mouse_and_keyboard_routes(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    def fakerun_command(cmd, timeout=10):
        return "", "", 0

    monkeypatch.setattr(input_control_module, "run_command", fakerun_command)

    move_response = await async_client.post(
        "/input/mouse/move",
        json={"x": 100, "y": 200},
        headers={"Authorization": f"Bearer {token}", "X-Confirm-Input": "true"},
    )
    assert move_response.status_code == 200
    assert move_response.json()["success"] is True

    click_response = await async_client.post(
        "/input/mouse/click",
        json={"x": 100, "y": 200, "button": "left"},
        headers={"Authorization": f"Bearer {token}", "X-Confirm-Input": "true"},
    )
    assert click_response.status_code == 200
    assert click_response.json()["success"] is True

    type_response = await async_client.post(
        "/input/keyboard/type",
        json={"text": "hello"},
        headers={"Authorization": f"Bearer {token}", "X-Confirm-Input": "true"},
    )
    assert type_response.status_code == 200
    assert type_response.json()["success"] is True

    key_response = await async_client.post(
        "/input/keyboard/key",
        json={"keys": ["ctrl", "c"]},
        headers={"Authorization": f"Bearer {token}", "X-Confirm-Input": "true"},
    )
    assert key_response.status_code == 200
    assert key_response.json()["success"] is True
