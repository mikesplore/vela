from typing import List, Optional

from fastapi import HTTPException

from domain.media import MediaStatus
from utils.run_command import run_command


def playerctl_command(args: List[str], player: Optional[str] = None) -> tuple[str, str, int]:
    cmd = ["playerctl"]
    if player:
        cmd.extend(["--player", player])
    cmd.extend(args)
    return run_command(cmd)


def _list_media_players() -> List[str]:
    stdout, stderr, code = playerctl_command(["-l"])
    if code != 0 or not stdout:
        return []
    return [line.strip() for line in stdout.splitlines() if line.strip()]


def parse_metadata_all(output: str) -> dict[str, dict[str, str]]:
    players: dict[str, dict[str, str]] = {}
    for line in output.splitlines():
        parts = line.split(None, 2)
        if len(parts) != 3:
            continue
        player, field, value = parts
        players.setdefault(player, {})[field] = value
    return players


def choose_player() -> Optional[str]:
    players = _list_media_players()
    if not players:
        stdout, stderr, code = playerctl_command(["metadata"])
        if code == 0 and stdout:
            metadata = parse_metadata_all(stdout)
            players = list(metadata.keys())

    if not players:
        return None

    for player in players:
        if "spotify" in player.lower():
            return player

    for player in players:
        stdout, stderr, code = playerctl_command(["status"], player=player)
        if code == 0 and stdout:
            return player

    return players[0]


def media_action(command: List[str], success_message: str) -> MediaStatus:
    stdout, stderr, code = run_command(command)
    if code != 0:
        raise HTTPException(status_code=500, detail=stderr or stdout or "media command failed")
    return MediaStatus(success=True, message=success_message)


def query_metadata(field: str, player: Optional[str] = None) -> Optional[str]:
    player = player or choose_player()
    if player:
        stdout, stderr, code = playerctl_command(["metadata", field], player=player)
        if code == 0 and stdout:
            return stdout
    else:
        stdout, stderr, code = playerctl_command(["metadata", field])
        if code == 0 and stdout:
            return stdout

    stdout, stderr, code = playerctl_command(["metadata"])
    if code != 0 or not stdout:
        return None
    metadata = parse_metadata_all(stdout)
    if player and player in metadata and field in metadata[player]:
        return metadata[player][field]
    for section in metadata.values():
        if field in section:
            return section[field]
    return None


def query_status(player: Optional[str] = None) -> Optional[str]:
    player = player or choose_player()
    if player:
        stdout, stderr, code = playerctl_command(["status"], player=player)
        if code == 0 and stdout:
            return stdout
    else:
        stdout, stderr, code = playerctl_command(["status"])
        if code == 0 and stdout:
            return stdout
    return None


def query_position(player: Optional[str] = None) -> Optional[float]:
    player = player or choose_player()
    if player:
        stdout, stderr, code = playerctl_command(["position"], player=player)
    else:
        stdout, stderr, code = playerctl_command(["position"])
    if code != 0 or not stdout:
        return None
    try:
        return float(stdout)
    except ValueError:
        return None


def query_length(player: Optional[str] = None) -> Optional[float]:
    player = player or choose_player()
    if player:
        stdout, stderr, code = playerctl_command(["metadata", "mpris:length"], player=player)
    else:
        stdout, stderr, code = playerctl_command(["metadata", "mpris:length"])
    if code != 0 or not stdout:
        return None
    try:
        return float(stdout) / 1_000_000
    except ValueError:
        return None
