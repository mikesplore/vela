from typing import Any
from fastapi import APIRouter, Depends
from app.dependencies import get_current_user
from domain.media import MediaStatus, SeekRequest, NowPlayingInfo
from services.media import media_action, choose_player, query_metadata, query_status, query_position, query_length

router = APIRouter(prefix="/media", tags=["media"])


@router.post("/play-pause", response_model=MediaStatus, dependencies=[Depends(get_current_user)])
async def play_pause() -> Any:
    """Toggle play/pause on the active media player."""
    return media_action(["playerctl", "play-pause"], "playback toggled")


@router.post("/next", response_model=MediaStatus, dependencies=[Depends(get_current_user)])
async def media_next() -> Any:
    """Skip to the next media track."""
    return media_action(["playerctl", "next"], "skipped to next track")


@router.post("/previous", response_model=MediaStatus, dependencies=[Depends(get_current_user)])
async def media_previous() -> Any:
    """Return to the previous media track."""
    return media_action(["playerctl", "previous"], "skipped to previous track")


@router.post("/seek", response_model=MediaStatus, dependencies=[Depends(get_current_user)])
async def seek_media(request: SeekRequest) -> Any:
    """Seek media playback to the requested position in seconds."""
    return media_action(["playerctl", "position", str(request.seconds)], "seeked playback")


@router.get("/now-playing", response_model=NowPlayingInfo, dependencies=[Depends(get_current_user)])
async def now_playing() -> Any:
    """Return current media metadata and playback position."""
    player = choose_player()
    art_url = query_metadata("mpris:artUrl", player=player)
    # Filter out local file URLs; only return remote HTTP(S) URLs
    if art_url and art_url.startswith("file://"):
        art_url = None
    status = query_status(player=player)
    return NowPlayingInfo(
        title=query_metadata("xesam:title", player=player),
        artist=query_metadata("xesam:artist", player=player),
        album=query_metadata("xesam:album", player=player),
        art_url=art_url,
        status=status,
        playing=status.lower() == "playing" if status else None,
        position_seconds=query_position(player=player),
        length_seconds=query_length(player=player),
    )
