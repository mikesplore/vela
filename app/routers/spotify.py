from typing import Any, Optional, List, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.services.spotify import (
    get_spotify_client,
    search_and_play,
    get_recommendations,
    play_by_genre,
    play_random_song,
)
from app.dependencies import get_current_user

spotify_router = APIRouter(prefix="/spotify", tags=["spotify"])

root_router = APIRouter()

# Alias kept for app/routers/__init__.py imports below
router = spotify_router

class SearchAndPlayRequest(BaseModel):
    query: str
    device_id: Optional[str] = None

class GetRecommendationsRequest(BaseModel):
    seed_track_query: str
    limit: int = 10
    auto_play: bool = False
    device_id: Optional[str] = None

class PlayByGenreRequest(BaseModel):
    genre: str
    limit: int = 20
    device_id: Optional[str] = None

class PlayRandomSongRequest(BaseModel):
    genre_pool: Optional[List[str]] = None
    device_id: Optional[str] = None


@root_router.get("/callback", dependencies=[Depends(get_current_user)])
async def root_spotify_callback(code: Optional[str] = None, state: Optional[str] = None) -> dict:
    if not code:
        raise HTTPException(status_code=400, detail="Missing Spotify authorization code")

    try:
        sp = get_spotify_client()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        token_info = sp.auth_manager.get_access_token(code, as_dict=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Spotify token exchange failed: {e}")

    try:
        sp.auth_manager._token_info = token_info
        sp.auth_manager._save_token_info(token_info)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save Spotify token: {e}")

    return {"status": "linked", "token_info": token_info}


@spotify_router.get("/auth", dependencies=[Depends(get_current_user)])
async def spotify_auth() -> dict:
    try:
        sp = get_spotify_client()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        auth_url = sp.auth_manager.get_authorize_url()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build Spotify auth URL: {e}")

    return {"auth_url": auth_url}


@spotify_router.get("/callback", dependencies=[Depends(get_current_user)])
async def spotify_callback(code: Optional[str] = None, state: Optional[str] = None) -> dict:
    if not code:
        raise HTTPException(status_code=400, detail="Missing Spotify authorization code")

    try:
        sp = get_spotify_client()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        token_info = sp.auth_manager.get_access_token(code, as_dict=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Spotify token exchange failed: {e}")

    try:
        sp.auth_manager._token_info = token_info
        sp.auth_manager._save_token_info(token_info)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save Spotify token: {e}")

    return {"status": "linked", "token_info": token_info}


@spotify_router.post("/search-and-play", dependencies=[Depends(get_current_user)])
async def search_and_play_route(request: SearchAndPlayRequest) -> dict:
    try:
        sp = get_spotify_client()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        return search_and_play(sp, request.query, device_id=request.device_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@spotify_router.post("/recommendations", dependencies=[Depends(get_current_user)])
async def recommendations_route(request: GetRecommendationsRequest) -> List[dict]:
    try:
        sp = get_spotify_client()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        return get_recommendations(
            sp,
            request.seed_track_query,
            limit=request.limit,
            auto_play=request.auto_play,
            device_id=request.device_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@spotify_router.post("/play-by-genre", dependencies=[Depends(get_current_user)])
async def play_by_genre_route(request: PlayByGenreRequest) -> List[dict]:
    try:
        sp = get_spotify_client()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        return play_by_genre(sp, request.genre, limit=request.limit, device_id=request.device_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@spotify_router.post("/play-random", dependencies=[Depends(get_current_user)])
async def play_random_route(request: PlayRandomSongRequest) -> dict:
    try:
        sp = get_spotify_client()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        return play_random_song(sp, genre_pool=request.genre_pool, device_id=request.device_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))