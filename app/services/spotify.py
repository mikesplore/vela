import html
import os
from typing import Optional, Dict, Any

from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from fastapi import HTTPException

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

def search_and_play(sp: spotipy.Spotify, query: str, device_id: Optional[str] = None) -> Dict[str, Any]:
    results = sp.search(q=query, type="track", limit=1)
    tracks = results["tracks"]["items"]
    if not tracks:
        raise HTTPException(status_code=404, detail=f"No tracks found for: '{query}'")

    track = tracks[0]
    sp.start_playback(device_id=device_id, uris=[track["uri"]])

    return {
        "name":   track["name"],
        "artist": track["artists"][0]["name"],
        "uri":    track["uri"],
        "url":    track["external_urls"]["spotify"],
    }


# ──────────────────────────────────────────────
# Get Available Devices
# ──────────────────────────────────────────────

def get_available_devices(sp: spotipy.Spotify) -> Dict[str, Any]:
    devices = sp.devices()
    return devices
