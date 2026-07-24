import base64

import pytest
from app.auth import create_access_token
from app.routers import display as display_module


@pytest.mark.anyio
async def test_display_screenshot_returns_base64(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    monkeypatch.setattr(display_module, "_capture_screenshot_with_flameshot", lambda: b"\x89PNG\r\n\x1a\n")

    response = await async_client.get(
        "/display/screenshot",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "image_base64" in payload
    assert payload.get("content_type") == "image/png"
    decoded = base64.b64decode(payload["image_base64"])
    assert decoded.startswith(b"\x89PNG")


@pytest.mark.anyio
async def test_display_screenshot_requires_flameshot(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    monkeypatch.setattr(display_module, "_capture_screenshot_with_flameshot", lambda: (_ for _ in ()).throw(RuntimeError("flameshot failed")))

    response = await async_client.get(
        "/display/screenshot",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 500
    payload = response.json()
    assert "flameshot" in payload["detail"].lower()


@pytest.mark.anyio
async def test_display_monitor_off_and_on(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    def fakerun_command(cmd, timeout=10):
        if cmd[:4] == ["busctl", "--user", "set-property", "org.gnome.Mutter.DisplayConfig"]:
            return "", "", 0
        return "", "", 0

    monkeypatch.setattr(display_module, "run_command", fakerun_command)

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
    assert "mutter" in off_resp.json()["message"].lower()
    assert on_resp.status_code == 200
    assert on_resp.json()["success"] is True
    assert "mutter" in on_resp.json()["message"].lower()


@pytest.mark.anyio
async def test_display_monitor_on_uses_mutter_power_save(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    calls = []

    def fakerun_command(cmd, timeout=10):
        calls.append(cmd)
        if cmd[:4] == ["busctl", "--user", "set-property", "org.gnome.Mutter.DisplayConfig"]:
            return "", "", 0
        return "", "", 1

    monkeypatch.setattr(display_module, "run_command", fakerun_command)

    response = await async_client.post(
        "/display/monitor/on",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert calls[0][:4] == ["busctl", "--user", "set-property", "org.gnome.Mutter.DisplayConfig"]


@pytest.mark.anyio
async def test_display_monitor_state_reads_mutter_power_save(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    def fakerun_command(cmd, timeout=10):
        if cmd == [
            "busctl",
            "--user",
            "get-property",
            "org.gnome.Mutter.DisplayConfig",
            "/org/gnome/Mutter/DisplayConfig",
            "org.gnome.Mutter.DisplayConfig",
            "PowerSaveMode",
        ]:
            return "i 1", "", 0
        return "", "", 1

    monkeypatch.setattr(display_module, "run_command", fakerun_command)

    response = await async_client.get(
        "/display/monitor/state",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["power_save_mode"] == 1
    assert payload["is_on"] is False


@pytest.mark.anyio
async def test_display_brightness_uses_backlight_fallback(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    calls = []

    def fakerun_command(cmd, timeout=10):
        calls.append(cmd)
        if cmd[:2] == ["brightnessctl", "set"]:
            return "", "", 0
        return "", "", 1

    monkeypatch.setattr(display_module, "run_command", fakerun_command)
    monkeypatch.setattr(display_module, "_first_connected_output", lambda: None)

    response = await async_client.post(
        "/display/brightness",
        json={"value": 40},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert calls and calls[0][:2] == ["brightnessctl", "set"]


@pytest.mark.anyio
async def test_display_brightness_uses_xrandr_fallback_when_backlight_command_fails(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    def fakerun_command(cmd, timeout=10):
        if cmd[:2] == ["xrandr", "--output"]:
            return "", "", 0
        return "", "", 1

    monkeypatch.setattr(display_module, "run_command", fakerun_command)
    monkeypatch.setattr(display_module, "_first_connected_output", lambda: "HDMI-1")

    response = await async_client.post(
        "/display/brightness",
        json={"value": 10},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.anyio
async def test_display_brightness_reads_sysfs_value(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    monkeypatch.setattr(display_module, "_get_brightness", lambda: 55.0)

    response = await async_client.get(
        "/display/brightness",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"brightness": 55.0}


@pytest.mark.anyio
async def test_display_rotate_get_alias(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    def fakerun_command(cmd, timeout=10):
        if cmd == ["xrandr", "--query"]:
            return "HDMI-1 connected primary 1920x1080+0+0", "", 0
        return "", "", 0

    monkeypatch.setattr(display_module, "run_command", fakerun_command)

    response = await async_client.get(
        "/display/rotate?orientation=left",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True


@pytest.mark.anyio
async def test_display_night_light(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    def fakerun_command(cmd, timeout=10):
        if "night-light-enabled" in cmd or "night-light-temperature" in cmd:
            return "", "", 0
        return "", "", 0

    monkeypatch.setattr(display_module, "run_command", fakerun_command)

    response = await async_client.post(
        "/display/night-light",
        json={"enabled": True, "temperature": 4000},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
