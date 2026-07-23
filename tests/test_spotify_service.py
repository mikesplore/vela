import pytest
from spotipy.exceptions import SpotifyException

from app.services import spotify as spotify_service


def test_search_and_play_retries_after_no_active_device(monkeypatch):
    class FakeSpotify:
        def __init__(self):
            self.start_calls: list[tuple[str | None, list[str]]] = []
            self.devices_calls = 0

        def search(self, q, type="track", limit=1):
            return {
                "tracks": {
                    "items": [{
                        "name": "Test Song",
                        "artists": [{"name": "Test Artist"}],
                        "uri": "spotify:track:123",
                        "external_urls": {"spotify": "https://open.spotify.com/track/123"},
                    }]
                }
            }

        def devices(self):
            self.devices_calls += 1
            if self.devices_calls >= 2:
                return {"devices": [{"id": "pc-device", "type": "Computer", "is_active": False}]}
            return {"devices": []}

        def transfer_playback(self, device_id, force_play=False):
            assert device_id == "pc-device"

        def start_playback(self, device_id=None, uris=None):
            self.start_calls.append((device_id, uris or []))
            if len(self.start_calls) == 1:
                raise SpotifyException(404, -1, "Player command failed: No active device found")

    fake = FakeSpotify()
    monkeypatch.setattr("app.services.processes.open_installed_application", lambda name: None)
    monkeypatch.setattr(spotify_service, "playerctl_command", lambda *args, **kwargs: ("", "", 0))
    monkeypatch.setattr(spotify_service.time, "sleep", lambda _seconds: None)

    result = spotify_service.search_and_play(fake, "Test Song")

    assert result["name"] == "Test Song"
    assert fake.start_calls[-1] == ("pc-device", ["spotify:track:123"])
