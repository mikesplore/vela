import base64

import pytest
from auth import create_access_token
from routers import display as display_module


@pytest.mark.anyio
async def test_display_screenshot_returns_base64(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    monkeypatch.setattr(display_module, "_capture_screenshot_with_gnome_screenshot", lambda: b"\x89PNG\r\n\x1a\n")

    response = await async_client.get(
        "/display/screenshot",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "image_base64" in payload
    decoded = base64.b64decode(payload["image_base64"])
    assert decoded.startswith(b"\x89PNG")


@pytest.mark.anyio
async def test_display_screenshot_requires_gnome_screenshot(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    monkeypatch.setattr(display_module, "_capture_screenshot_with_gnome_screenshot", lambda: (_ for _ in ()).throw(RuntimeError("gnome-screenshot failed")))

    response = await async_client.get(
        "/display/screenshot",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 500
    payload = response.json()
    assert "gnome-screenshot" in payload["detail"].lower()


@pytest.mark.anyio
async def test_display_monitor_off_and_on(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    def fake_run_command(cmd, timeout=10):
        return "", "", 0

    monkeypatch.setattr(display_module, "_run_command", fake_run_command)

    off_resp = await async_client.post(
        "/display/monitor/off",
        headers={"Authorization": f"Bearer {token}"},
    )
    on_resp = await async_client.post(
        "/display/monitor/on",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert off_resp.status_code == 200
    assert off_resp.json()["success"] is True
    assert on_resp.status_code == 200
    assert on_resp.json()["success"] is True


@pytest.mark.anyio
async def test_display_rotate_get_alias(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    def fake_run_command(cmd, timeout=10):
        if cmd == ["xrandr", "--query"]:
            return "HDMI-1 connected primary 1920x1080+0+0", "", 0
        return "", "", 0

    monkeypatch.setattr(display_module, "_run_command", fake_run_command)

    response = await async_client.get(
        "/display/rotate?orientation=left",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
