from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.services.spotify import (
    get_spotify_client,
    search_and_play,
    get_available_devices,
    complete_spotify_link,
    oauth_result_page,
)
from app.dependencies import get_current_user

spotify_router = APIRouter(prefix="/spotify", tags=["spotify"])
# Alias for older VPS builds that forward OAuth to /callback instead of /spotify/callback.
spotify_callback_alias_router = APIRouter(tags=["spotify"])


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


async def _handle_oauth_callback(
        code: Optional[str] = None,
        error: Optional[str] = None,
        error_description: Optional[str] = None,
) -> HTMLResponse:
    """Public browser landing page after Spotify OAuth redirect."""
    if error:
        detail = error_description or error
        return HTMLResponse(
            content=oauth_result_page(
                title="Spotify sign-in failed",
                message=f"Spotify returned an error: {detail}",
                ok=False,
            ),
            status_code=400,
        )

    if not code:
        return HTMLResponse(
            content=oauth_result_page(
                title="Spotify sign-in failed",
                message="Missing authorization code from Spotify. Try signing in again.",
                ok=False,
            ),
            status_code=400,
        )

    try:
        complete_spotify_link(code)
    except HTTPException as exc:
        return HTMLResponse(
            content=oauth_result_page(
                title="Spotify sign-in failed",
                message=str(exc.detail),
                ok=False,
            ),
            status_code=exc.status_code,
        )
    except Exception as exc:
        return HTMLResponse(
            content=oauth_result_page(
                title="Spotify sign-in failed",
                message=f"Could not finish linking: {exc}",
                ok=False,
            ),
            status_code=400,
        )

    return HTMLResponse(
        content=oauth_result_page(
            title="Spotify linked",
            message="Sign-in succeeded. You can close this tab and return to Vela.",
            ok=True,
        ),
        status_code=200,
    )


@spotify_router.get("/callback", response_class=HTMLResponse)
async def spotify_callback(
        code: Optional[str] = Query(None),
        error: Optional[str] = Query(None),
        error_description: Optional[str] = Query(None),
) -> HTMLResponse:
    return await _handle_oauth_callback(code=code, error=error, error_description=error_description)


@spotify_callback_alias_router.get("/callback", response_class=HTMLResponse)
async def spotify_callback_alias(
        code: Optional[str] = Query(None),
        error: Optional[str] = Query(None),
        error_description: Optional[str] = Query(None),
) -> HTMLResponse:
    return await _handle_oauth_callback(code=code, error=error, error_description=error_description)


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
