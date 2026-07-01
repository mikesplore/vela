import os
from typing import Optional, List, Dict, Any

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
        open_browser=True,
    )
    sp = spotipy.Spotify(auth_manager=auth_manager)
    return sp


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
