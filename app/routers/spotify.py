from typing import Any, Optional, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.services.spotify import (
    get_spotify_client,
    search_and_play,
    get_available_devices,
)
from app.dependencies import get_current_user

spotify_router = APIRouter(prefix="/spotify", tags=["spotify"])

class SearchAndPlayRequest(BaseModel):
    query: str
    device_id: Optional[str] = None


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


@spotify_router.get("/devices", dependencies=[Depends(get_current_user)])
async def get_devices() -> dict:
    try:
        sp = get_spotify_client()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        return get_available_devices(sp)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
