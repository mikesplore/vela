import os
import random
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
# 1. Search for a Song and Play It
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
# 2. Get Recommendations for a Song
# ──────────────────────────────────────────────

def get_recommendations(
    sp: spotipy.Spotify,
    seed_track_query: str,
    limit: int = 10,
    auto_play: bool = False,
    device_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    results = sp.search(q=seed_track_query, type="track", limit=1)
    tracks = results["tracks"]["items"]
    if not tracks:
        raise HTTPException(status_code=404, detail=f"Seed track not found: '{seed_track_query}'")

    _require_authenticated(sp)
    seed_id = tracks[0]["id"]
    recs = sp.recommendations(seed_tracks=[seed_id], limit=limit)

    recommended = [
        {
            "name":   t["name"],
            "artist": t["artists"][0]["name"],
            "uri":    t["uri"],
            "url":    t["external_urls"]["spotify"],
        }
        for t in recs["tracks"]
    ]

    if auto_play and recommended:
        uris = [t["uri"] for t in recommended]
        sp.start_playback(device_id=device_id, uris=uris)

    return recommended


# ──────────────────────────────────────────────
# 3. Play Songs by Genre
# ──────────────────────────────────────────────

def _require_authenticated(sp: spotipy.Spotify) -> None:
    try:
        current = sp.current_user()
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Spotify is not linked: {exc}")


def play_by_genre(
    sp: spotipy.Spotify,
    genre: str,
    limit: int = 20,
    device_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    _require_authenticated(sp)
    valid_genres = sp.recommendation_genre_seeds()["genres"]
    if genre.lower() not in valid_genres:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown genre '{genre}'. "
                f"Valid options include: {', '.join(valid_genres[:15])}…"
            ),
        )

    recs = sp.recommendations(seed_genres=[genre.lower()], limit=limit)
    playlist = [
        {
            "name":   t["name"],
            "artist": t["artists"][0]["name"],
            "uri":    t["uri"],
            "url":    t["external_urls"]["spotify"],
        }
        for t in recs["tracks"]
    ]

    if playlist:
        sp.start_playback(device_id=device_id, uris=[t["uri"] for t in playlist])

    return playlist


# ──────────────────────────────────────────────
# 4. Play a Random Song
# ──────────────────────────────────────────────

_RANDOM_GENRES = [
    "pop", "rock", "hip-hop", "jazz", "classical",
    "electronic", "r-n-b", "country", "reggae", "afrobeat",
]


def play_random_song(
    sp: spotipy.Spotify,
    genre_pool: Optional[List[str]] = None,
    device_id: Optional[str] = None,
) -> Dict[str, Any]:
    _require_authenticated(sp)
    pool  = genre_pool or _RANDOM_GENRES
    genre = random.choice(pool)

    recs  = sp.recommendations(seed_genres=[genre], limit=50)
    items = recs["tracks"]
    if not items:
        raise RuntimeError(f"No tracks returned for genre '{genre}'.")

    track = random.choice(items)
    sp.start_playback(device_id=device_id, uris=[track["uri"]])

    return {
        "name":   track["name"],
        "artist": track["artists"][0]["name"],
        "uri":    track["uri"],
        "url":    track["external_urls"]["spotify"],
        "genre":  genre,
    }