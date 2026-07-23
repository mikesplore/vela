import html
import logging
import os
import time
from typing import Optional, Dict, Any

from dotenv import load_dotenv
import spotipy
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyOAuth
from fastapi import HTTPException

from app.services.media import playerctl_command

logger = logging.getLogger(__name__)

load_dotenv()

SCOPES = [
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
    "streaming",
]


def get_spotify_client() -> spotipy.Spotify:
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI")

    if not all([client_id, client_secret, redirect_uri]):
        raise HTTPException(
            status_code=500,
            detail="Spotify is not configured. Please set SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, and SPOTIFY_REDIRECT_URI in .env.",
        )

    auth_manager = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=" ".join(SCOPES),
        cache_path=".spotify_token_cache",
        open_browser=False,
    )
    sp = spotipy.Spotify(auth_manager=auth_manager)
    return sp


def complete_spotify_link(code: str) -> None:
    """Exchange an OAuth authorization code and persist the Spotify token cache."""
    sp = get_spotify_client()
    token_info = sp.auth_manager.get_access_token(code, as_dict=True, check_cache=False)
    if not token_info or not token_info.get("access_token"):
        raise ValueError("Spotify token exchange returned no access token")
    sp.auth_manager.cache_handler.save_token_to_cache(token_info)


def oauth_result_page(*, title: str, message: str, ok: bool) -> str:
    """Simple browser page shown after Spotify redirects back to Vela."""
    accent = "#1DB954" if ok else "#c0392b"
    safe_title = html.escape(title)
    safe_message = html.escape(message)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <style>
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      font-family: Georgia, "Times New Roman", serif;
      background: #0f1410;
      color: #e8efe9;
    }}
    main {{
      width: min(28rem, calc(100% - 2rem));
      padding: 2rem;
      border-top: 4px solid {accent};
    }}
    h1 {{
      margin: 0 0 0.75rem;
      font-size: 1.6rem;
      font-weight: 600;
    }}
    p {{
      margin: 0;
      line-height: 1.5;
      color: #b7c4ba;
    }}
  </style>
</head>
<body>
  <main>
    <h1>{safe_title}</h1>
    <p>{safe_message}</p>
  </main>
</body>
</html>
"""


# ──────────────────────────────────────────────
# Search for a Song and Play It
# ──────────────────────────────────────────────

def _is_no_active_device_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "no active device" in text or "no device" in text


def _pick_spotify_device(sp: spotipy.Spotify) -> str | None:
    devices = sp.devices().get("devices") or []
    if not devices:
        return None
    for device in devices:
        if device.get("is_active"):
            return device["id"]
    for device in devices:
        if str(device.get("type", "")).lower() == "computer":
            return device["id"]
    return devices[0]["id"]


def _wait_for_spotify_device(sp: spotipy.Spotify, *, timeout: float = 15.0) -> str | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        device_id = _pick_spotify_device(sp)
        if device_id:
            return device_id
        time.sleep(0.5)
    return None


def _activate_local_spotify_device(sp: spotipy.Spotify) -> str | None:
    """Open Spotify locally and wait until Spotify Connect sees this PC."""
    from app.services.processes import ApplicationLaunchError, open_installed_application

    try:
        open_installed_application("spotify")
    except ApplicationLaunchError as exc:
        logger.warning("Spotify launch during playback recovery failed: %s", exc)
    except Exception as exc:
        logger.warning("Spotify launch during playback recovery failed: %s", exc)

    playerctl_command(["play"], player="spotify")
    time.sleep(1.0)

    device_id = _wait_for_spotify_device(sp)
    if not device_id:
        return None
    try:
        sp.transfer_playback(device_id=device_id, force_play=False)
    except SpotifyException as exc:
        logger.debug("Spotify transfer_playback skipped: %s", exc)
    return device_id


def search_and_play(sp: spotipy.Spotify, query: str, device_id: Optional[str] = None) -> Dict[str, Any]:
    results = sp.search(q=query, type="track", limit=1)
    tracks = results["tracks"]["items"]
    if not tracks:
        raise HTTPException(status_code=404, detail=f"No tracks found for: '{query}'")

    track = tracks[0]
    uri = track["uri"]
    target_device = device_id or _pick_spotify_device(sp)

    try:
        sp.start_playback(device_id=target_device, uris=[uri])
    except (SpotifyException, Exception) as exc:
        if device_id or not _is_no_active_device_error(exc):
            if isinstance(exc, SpotifyException):
                raise HTTPException(status_code=exc.http_status or 502, detail=str(exc)) from exc
            raise
        activated = _activate_local_spotify_device(sp)
        if not activated:
            raise HTTPException(
                status_code=503,
                detail=(
                    "No active Spotify device. Opened Spotify locally but it did not register "
                    "as a playback device in time."
                ),
            ) from exc
        try:
            sp.start_playback(device_id=activated, uris=[uri])
        except SpotifyException as retry_exc:
            raise HTTPException(status_code=retry_exc.http_status or 502, detail=str(retry_exc)) from retry_exc

    return {
        "name":   track["name"],
        "artist": track["artists"][0]["name"],
        "uri":    uri,
        "url":    track["external_urls"]["spotify"],
    }


# ──────────────────────────────────────────────
# Get Available Devices
# ──────────────────────────────────────────────

def get_available_devices(sp: spotipy.Spotify) -> Dict[str, Any]:
    devices = sp.devices()
    return devices
