import pytest

from auth import create_access_token
from routers import media as media_module


@pytest.mark.anyio
async def test_media_playback_controls(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    def fake_run_command(cmd, timeout=10):
        return "", "", 0

    monkeypatch.setattr(media_module, "_run_command", fake_run_command)

    pause_response = await async_client.post(
        "/media/play-pause",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert pause_response.status_code == 200
    assert pause_response.json()["success"] is True

    next_response = await async_client.post(
        "/media/next",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert next_response.status_code == 200
    assert next_response.json()["success"] is True

    prev_response = await async_client.post(
        "/media/previous",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert prev_response.status_code == 200
    assert prev_response.json()["success"] is True

    seek_response = await async_client.post(
        "/media/seek",
        json={"seconds": 12.5},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert seek_response.status_code == 200
    assert seek_response.json()["success"] is True


@pytest.mark.anyio
async def test_media_now_playing(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    def fake_run_command(cmd, timeout=10):
        if cmd == ["playerctl", "-l"]:
            return "", "", 1
        if cmd == ["playerctl", "metadata"]:
            return "spotify xesam:title Test Song\nspotify xesam:artist Test Artist\nspotify xesam:album Test Album\nspotify mpris:length 120000000\nspotify mpris:artUrl https://i.scdn.co/image/test", "", 0
        if cmd == ["playerctl", "--player", "spotify", "metadata", "xesam:title"]:
            return "Test Song", "", 0
        if cmd == ["playerctl", "--player", "spotify", "metadata", "xesam:artist"]:
            return "Test Artist", "", 0
        if cmd == ["playerctl", "--player", "spotify", "metadata", "xesam:album"]:
            return "Test Album", "", 0
        if cmd == ["playerctl", "--player", "spotify", "status"]:
            return "Playing", "", 0
        if cmd == ["playerctl", "--player", "spotify", "position"]:
            return "42.0", "", 0
        if cmd == ["playerctl", "--player", "spotify", "metadata", "mpris:length"]:
            return "120000000", "", 0
        return "", "", 1

    monkeypatch.setattr(media_module, "_run_command", fake_run_command)

    response = await async_client.get(
        "/media/now-playing",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Test Song"
    assert payload["artist"] == "Test Artist"
    assert payload["art_url"] == "https://i.scdn.co/image/test"
    assert payload["status"] == "Playing"
    assert payload["playing"] is True
    assert payload["position_seconds"] == 42.0
    assert payload["length_seconds"] == 120.0


def test_choose_player_prefers_spotify(monkeypatch):
    def fake_run_command(cmd, timeout=10):
        if cmd == ["playerctl", "-l"]:
            return "chromium\nspotify\nvlc", "", 0
        if cmd == ["playerctl", "--player", "spotify", "status"]:
            return "Playing", "", 0
        return "", "", 1

    monkeypatch.setattr(media_module, "_run_command", fake_run_command)
    assert media_module._choose_player() == "spotify"


def test_choose_player_selects_active_non_spotify(monkeypatch):
    def fake_run_command(cmd, timeout=10):
        if cmd == ["playerctl", "-l"]:
            return "chromium\nvlc", "", 0
        if cmd == ["playerctl", "--player", "chromium", "status"]:
            return "", "", 1
        if cmd == ["playerctl", "--player", "vlc", "status"]:
            return "Playing", "", 0
        return "", "", 1

    monkeypatch.setattr(media_module, "_run_command", fake_run_command)
    assert media_module._choose_player() == "vlc"
