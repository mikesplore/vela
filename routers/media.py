import subprocess
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dependencies import get_current_user

router = APIRouter(prefix="/media", tags=["media"])


class MediaStatus(BaseModel):
    success: bool
    message: str


class SeekRequest(BaseModel):
    seconds: float = Field(...)


class NowPlayingInfo(BaseModel):
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    art_url: Optional[str] = None
    status: Optional[str] = None
    playing: Optional[bool] = None
    position_seconds: Optional[float] = None
    length_seconds: Optional[float] = None


def _run_command(cmd: List[str], timeout: int = 10) -> tuple[str, str, int]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        return "", str(exc), 1


def _playerctl_command(args: List[str], player: Optional[str] = None) -> tuple[str, str, int]:
    cmd = ["playerctl"]
    if player:
        cmd.extend(["--player", player])
    cmd.extend(args)
    return _run_command(cmd)


def _list_media_players() -> List[str]:
    stdout, stderr, code = _playerctl_command(["-l"])
    if code != 0 or not stdout:
        return []
    return [line.strip() for line in stdout.splitlines() if line.strip()]


def _parse_metadata_all(output: str) -> dict[str, dict[str, str]]:
    players: dict[str, dict[str, str]] = {}
    for line in output.splitlines():
        parts = line.split(None, 2)
        if len(parts) != 3:
            continue
        player, field, value = parts
        players.setdefault(player, {})[field] = value
    return players


def _choose_player() -> Optional[str]:
    players = _list_media_players()
    if not players:
        stdout, stderr, code = _playerctl_command(["metadata"])
        if code == 0 and stdout:
            metadata = _parse_metadata_all(stdout)
            players = list(metadata.keys())

    if not players:
        return None

    for player in players:
        if "spotify" in player.lower():
            return player

    for player in players:
        stdout, stderr, code = _playerctl_command(["status"], player=player)
        if code == 0 and stdout:
            return player

    return players[0]


def _media_action(command: List[str], success_message: str) -> MediaStatus:
    stdout, stderr, code = _run_command(command)
    if code != 0:
        raise HTTPException(status_code=500, detail=stderr or stdout or "media command failed")
    return MediaStatus(success=True, message=success_message)


def _query_metadata(field: str, player: Optional[str] = None) -> Optional[str]:
    player = player or _choose_player()
    if player:
        stdout, stderr, code = _playerctl_command(["metadata", field], player=player)
        if code == 0 and stdout:
            return stdout
    else:
        stdout, stderr, code = _playerctl_command(["metadata", field])
        if code == 0 and stdout:
            return stdout

    stdout, stderr, code = _playerctl_command(["metadata"])
    if code != 0 or not stdout:
        return None
    metadata = _parse_metadata_all(stdout)
    if player and player in metadata and field in metadata[player]:
        return metadata[player][field]
    for section in metadata.values():
        if field in section:
            return section[field]
    return None


def _query_status(player: Optional[str] = None) -> Optional[str]:
    player = player or _choose_player()
    if player:
        stdout, stderr, code = _playerctl_command(["status"], player=player)
        if code == 0 and stdout:
            return stdout
    else:
        stdout, stderr, code = _playerctl_command(["status"])
        if code == 0 and stdout:
            return stdout
    return None


def _query_position(player: Optional[str] = None) -> Optional[float]:
    player = player or _choose_player()
    if player:
        stdout, stderr, code = _playerctl_command(["position"], player=player)
    else:
        stdout, stderr, code = _playerctl_command(["position"])
    if code != 0 or not stdout:
        return None
    try:
        return float(stdout)
    except ValueError:
        return None


def _query_length(player: Optional[str] = None) -> Optional[float]:
    player = player or _choose_player()
    if player:
        stdout, stderr, code = _playerctl_command(["metadata", "mpris:length"], player=player)
    else:
        stdout, stderr, code = _playerctl_command(["metadata", "mpris:length"])
    if code != 0 or not stdout:
        return None
    try:
        return float(stdout) / 1_000_000
    except ValueError:
        return None


@router.post("/play-pause", response_model=MediaStatus, dependencies=[Depends(get_current_user)])
async def play_pause() -> Any:
    """Toggle play/pause on the active media player."""
    return _media_action(["playerctl", "play-pause"], "playback toggled")


@router.post("/next", response_model=MediaStatus, dependencies=[Depends(get_current_user)])
async def media_next() -> Any:
    """Skip to the next media track."""
    return _media_action(["playerctl", "next"], "skipped to next track")


@router.post("/previous", response_model=MediaStatus, dependencies=[Depends(get_current_user)])
async def media_previous() -> Any:
    """Return to the previous media track."""
    return _media_action(["playerctl", "previous"], "skipped to previous track")


@router.post("/seek", response_model=MediaStatus, dependencies=[Depends(get_current_user)])
async def seek_media(request: SeekRequest) -> Any:
    """Seek media playback to the requested position in seconds."""
    return _media_action(["playerctl", "position", str(request.seconds)], "seeked playback")


@router.get("/now-playing", response_model=NowPlayingInfo, dependencies=[Depends(get_current_user)])
async def now_playing() -> Any:
    """Return current media metadata and playback position."""
    player = _choose_player()
    art_url = _query_metadata("mpris:artUrl", player=player)
    # Filter out local file URLs; only return remote HTTP(S) URLs
    if art_url and art_url.startswith("file://"):
        art_url = None
    status = _query_status(player=player)
    return NowPlayingInfo(
        title=_query_metadata("xesam:title", player=player),
        artist=_query_metadata("xesam:artist", player=player),
        album=_query_metadata("xesam:album", player=player),
        art_url=art_url,
        status=status,
        playing=status.lower() == "playing" if status else None,
        position_seconds=_query_position(player=player),
        length_seconds=_query_length(player=player),
    )
