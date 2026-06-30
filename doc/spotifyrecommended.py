"""
Spotify Integration Client
Required .env variables:
    SPOTIFY_CLIENT_ID       - Your Spotify app client ID
    SPOTIFY_CLIENT_SECRET   - Your Spotify app client secret
"""

import random
from http.server import  BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv
import spotipy
from app.utils.spotify_client import get_spotify_client

load_dotenv()

# ──────────────────────────────────────────────
# Auth & Client Setup
# ──────────────────────────────────────────────

SCOPES = [
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
    "streaming",
]

# ──────────────────────────────────────────────
# Callback Handler (edit redirect logic as needed)
# ──────────────────────────────────────────────

class CallbackHandler(BaseHTTPRequestHandler):
    """
    Minimal local HTTP server to handle the Spotify OAuth callback.
    """
    auth_code: str | None = None

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/callback":                       # <-- edit if needed
            params = parse_qs(parsed.query)
            CallbackHandler.auth_code = params.get("code", [None])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Auth successful. You can close this tab.")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *_):
        pass  # silence server logs


# ──────────────────────────────────────────────
# 1. Search for a Song and Play It
# ──────────────────────────────────────────────

def search_and_play(sp: spotipy.Spotify, query: str, device_id: str | None = None) -> dict:
    """
    Search Spotify for a track and immediately play it.

    Args:
        sp:         Authenticated Spotify client.
        query:      Search string, e.g. "Bohemian Rhapsody Queen".
        device_id:  Target device ID. Uses active device if None.

    Returns:
        dict with 'name', 'artist', 'uri', and 'url' of the track played.

    Raises:
        ValueError: No results found for the query.
    """
    results = sp.search(q=query, type="track", limit=1)
    tracks = results["tracks"]["items"]
    if not tracks:
        raise ValueError(f"No tracks found for: '{query}'")

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
    device_id: str | None = None,
) -> list[dict]:
    """
    Return track recommendations based on a seed song.

    Args:
        sp:               Authenticated Spotify client.
        seed_track_query: Song name to base recommendations on.
        limit:            Number of recommendations to return (1–100).
        auto_play:        If True, queues all recommendations on the active device.
        device_id:        Target device ID (used only when auto_play=True).

    Returns:
        List of dicts, each with 'name', 'artist', 'uri', and 'url'.

    Raises:
        ValueError: Seed track not found.
    """
    results = sp.search(q=seed_track_query, type="track", limit=1)
    tracks = results["tracks"]["items"]
    if not tracks:
        raise ValueError(f"Seed track not found: '{seed_track_query}'")

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

def play_by_genre(
    sp: spotipy.Spotify,
    genre: str,
    limit: int = 20,
    device_id: str | None = None,
) -> list[dict]:
    """
    Fetch recommendations for a genre and start playback.

    Args:
        sp:         Authenticated Spotify client.
        genre:      A Spotify genre seed, e.g. "jazz", "hip-hop", "afrobeat".
                    Call sp.recommendation_genre_seeds() for the full list.
        limit:      Number of tracks to queue (1–100).
        device_id:  Target device ID. Uses active device if None.

    Returns:
        List of dicts with 'name', 'artist', 'uri', and 'url' for each track.

    Raises:
        ValueError: Genre not recognised by Spotify.
    """
    valid_genres = sp.recommendation_genre_seeds()["genres"]
    if genre.lower() not in valid_genres:
        raise ValueError(
            f"Unknown genre '{genre}'. "
            f"Valid options include: {', '.join(valid_genres[:15])}…"
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
    genre_pool: list[str] | None = None,
    device_id: str | None = None,
) -> dict:
    """
    Pick a random genre, fetch recommendations, and play a single random track.

    Args:
        sp:          Authenticated Spotify client.
        genre_pool:  Optional list of genres to pick from.
                     Defaults to a broad built-in selection.
        device_id:   Target device ID. Uses active device if None.

    Returns:
        dict with 'name', 'artist', 'uri', 'url', and 'genre' of the track played.
    """
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


# ──────────────────────────────────────────────
# Quick demo (remove or guard in production)
# ──────────────────────────────────────────────

if __name__ == "__main__":
    sp = get_spotify_client()

    print("\n── Search & Play ──")
    result = search_and_play(sp, "Blinding Lights The Weeknd")
    print(f"Now playing: {result['name']} — {result['artist']}")

    print("\n── Recommendations ──")
    recs = get_recommendations(sp, "Blinding Lights The Weeknd", limit=5)
    for r in recs:
        print(f"  • {r['name']} — {r['artist']}")

    print("\n── Play by Genre: afrobeat ──")
    tracks = play_by_genre(sp, "afrobeat", limit=10)
    print(f"Queued {len(tracks)} afrobeat tracks.")

    print("\n── Random Song ──")
    rand = play_random_song(sp)
    print(f"Random pick: {rand['name']} — {rand['artist']} (genre: {rand['genre']})")