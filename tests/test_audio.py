import pytest

from auth import create_access_token
from routers import audio as audio_module


@pytest.mark.anyio
async def test_audio_volume_get(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    sample = "Simple mixer control 'Master',0\n  Playback channels: Front Left - Front Right\n  Mono:\n  Front Left: Playback 74 [74%] [on]\n"

    def fake_run_command(cmd, timeout=10):
        if cmd[:3] == ["amixer", "get", "Master"]:
            return sample, "", 0
        return "", "", 0

    monkeypatch.setattr(audio_module, "_run_command", fake_run_command)

    response = await async_client.get(
        "/audio/volume",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["volume"] == 74
    assert payload["muted"] is False


@pytest.mark.anyio
async def test_audio_devices_returns_list(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    def fake_run_command(cmd, timeout=10):
        if cmd == ["pactl", "list", "short", "sinks"]:
            return "0\talsa_output.test\t...", "", 0
        if cmd == ["pactl", "list", "short", "sources"]:
            return "0\talsa_input.test\t...", "", 0
        return "", "", 0

    monkeypatch.setattr(audio_module, "_run_command", fake_run_command)

    response = await async_client.get(
        "/audio/devices",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    devices = response.json()
    assert any(device["type"] == "sink" for device in devices)
    assert any(device["type"] == "source" for device in devices)


@pytest.mark.anyio
async def test_audio_devices_friendly_names(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    def fake_run_command(cmd, timeout=10):
        if cmd == ["pactl", "list", "short", "sinks"]:
            return "0\talsa_output.test.HiFi__Speaker__sink\t...", "", 0
        if cmd == ["pactl", "list", "short", "sources"]:
            return "1\talsa_input.test.Mic__source\t...", "", 0
        if cmd == ["pactl", "list", "sinks"]:
            return "Name: alsa_output.test.HiFi__Speaker__sink\nDescription: Built-in Audio Analog Stereo\n", "", 0
        if cmd == ["pactl", "list", "sources"]:
            return "Name: alsa_input.test.Mic__source\nDescription: Built-in Microphone\n", "", 0
        return "", "", 0

    monkeypatch.setattr(audio_module, "_run_command", fake_run_command)

    response = await async_client.get(
        "/audio/devices",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    devices = response.json()
    assert any(device["name"] == "Built-in Audio Analog Stereo" for device in devices)
    assert any(device["name"] == "Built-in Microphone" for device in devices)


@pytest.mark.anyio
async def test_beep_endpoint(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    calls = []

    def fake_run_command(cmd, timeout=10):
        calls.append(cmd)
        if cmd == ["paplay", "/usr/share/sounds/freedesktop/stereo/bell.oga"]:
            return "", "", 0
        return "", "", 0

    monkeypatch.setattr(audio_module, "_run_command", fake_run_command)

    response = await async_client.post(
        "/audio/beep",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert any(call[0] == "paplay" for call in calls)


@pytest.mark.anyio
async def test_audio_output_devices_alias(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    def fake_run_command(cmd, timeout=10):
        if cmd == ["pactl", "list", "short", "sinks"]:
            return "0\talsa_output.test\t...", "", 0
        if cmd == ["pactl", "list", "short", "sources"]:
            return "0\talsa_input.test\t...", "", 0
        return "", "", 0

    monkeypatch.setattr(audio_module, "_run_command", fake_run_command)

    response = await async_client.get(
        "/audio/output-devices",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    devices = response.json()
    assert any(device["type"] == "sink" for device in devices)
    assert any(device["type"] == "source" for device in devices)
