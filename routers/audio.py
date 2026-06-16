import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dependencies import get_current_user

router = APIRouter(prefix="/audio", tags=["audio"])


class VolumeInfo(BaseModel):
    volume: int
    muted: bool


class VolumeRequest(BaseModel):
    value: int = Field(..., ge=0, le=100)


class StepRequest(BaseModel):
    step: int = Field(..., gt=0, le=20)


class MuteRequest(BaseModel):
    muted: bool


class AudioDevice(BaseModel):
    id: str
    name: str
    type: str


class ActionResponse(BaseModel):
    success: bool
    message: str


class OutputDeviceRequest(BaseModel):
    device_id: str


def _run_command(cmd: List[str], timeout: int = 10) -> tuple[str, str, int]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        return "", str(exc), 1


def _parse_volume(output: str) -> VolumeInfo:
    match = re.search(r"\[(\d{1,3})%\].*\[(on|off)\]", output)
    if not match:
        raise ValueError("could not parse volume")
    return VolumeInfo(volume=int(match.group(1)), muted=(match.group(2) == "off"))


def _audio_command(command: List[str]) -> None:
    stdout, stderr, code = _run_command(command)
    if code != 0:
        raise HTTPException(status_code=500, detail=stderr or stdout or "audio command failed")


def _get_volume() -> VolumeInfo:
    stdout, stderr, code = _run_command(["amixer", "get", "Master"])
    if code != 0 or not stdout:
        raise HTTPException(status_code=500, detail=stderr or stdout or "failed to query volume")
    return _parse_volume(stdout)


def _get_device_descriptions(command: List[str]) -> Dict[str, str]:
    stdout, stderr, code = _run_command(command)
    if code != 0 or not stdout:
        return {}

    descriptions: Dict[str, str] = {}
    current_name: str | None = None
    for line in stdout.splitlines():
        raw_line = line.strip()
        if raw_line.startswith("Name:"):
            current_name = raw_line.split(":", 1)[1].strip()
        elif raw_line.startswith("Description:") and current_name:
            descriptions[current_name] = raw_line.split(":", 1)[1].strip()
            current_name = None
    return descriptions


def _friendly_device_name(raw_name: str, description: str = "") -> str:
    if description:
        return description
    cleaned = raw_name
    if "." in cleaned:
        cleaned = cleaned.split(".", 1)[-1]
    cleaned = cleaned.replace("__", " ").replace("_", " ")
    cleaned = cleaned.replace("sink", "").replace("source", "").strip()
    return cleaned or raw_name


def _list_devices(command: List[str], desc_command: List[str], dev_type: str) -> List[AudioDevice]:
    descriptions = _get_device_descriptions(desc_command)
    stdout, stderr, code = _run_command(command)
    if code != 0 or not stdout:
        return []
    devices: List[AudioDevice] = []
    for line in stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            raw_name = parts[1]
            friendly_name = _friendly_device_name(raw_name, descriptions.get(raw_name, ""))
            devices.append(AudioDevice(id=parts[0], name=friendly_name, type=dev_type))
    return devices


def _play_beep() -> None:
    if Path("/usr/share/sounds/freedesktop/stereo/bell.oga").exists():
        _audio_command(["paplay", "/usr/share/sounds/freedesktop/stereo/bell.oga"])
        return

    stdout, stderr, code = _run_command(["canberra-gtk-play", "--id", "bell"])
    if code == 0:
        return

    if Path("/usr/share/sounds/alsa/Front_Center.wav").exists():
        _audio_command(["aplay", "/usr/share/sounds/alsa/Front_Center.wav"])
        return

    _audio_command(["bash", "-lc", "printf '\\a'"])


@router.get("/volume", response_model=VolumeInfo, dependencies=[Depends(get_current_user)])
async def audio_volume() -> Any:
    """Get current master volume and mute state."""
    return _get_volume()


@router.post("/volume", response_model=VolumeInfo, dependencies=[Depends(get_current_user)])
async def set_volume(request: VolumeRequest) -> Any:
    """Set the master volume level."""
    _audio_command(["amixer", "set", "Master", f"{request.value}%"])
    return _get_volume()


@router.post("/volume/up", response_model=VolumeInfo, dependencies=[Depends(get_current_user)])
async def volume_up(request: StepRequest) -> Any:
    """Increase the master volume by a step."""
    _audio_command(["amixer", "set", "Master", f"{request.step}%+"])
    return _get_volume()


@router.get("/volume/up", response_model=VolumeInfo, dependencies=[Depends(get_current_user)])
async def volume_up_get(step: int = 5) -> Any:
    """Increase the master volume by a step via query parameter."""
    return await volume_up(StepRequest(step=step))


@router.post("/volume/down", response_model=VolumeInfo, dependencies=[Depends(get_current_user)])
async def volume_down(request: StepRequest) -> Any:
    """Decrease the master volume by a step."""
    _audio_command(["amixer", "set", "Master", f"{request.step}%-"])
    return _get_volume()


@router.get("/volume/down", response_model=VolumeInfo, dependencies=[Depends(get_current_user)])
async def volume_down_get(step: int = 5) -> Any:
    """Decrease the master volume by a step via query parameter."""
    return await volume_down(StepRequest(step=step))


@router.post("/mute", response_model=VolumeInfo, dependencies=[Depends(get_current_user)])
async def mute_audio(request: MuteRequest) -> Any:
    """Mute or unmute the master audio channel."""
    command = ["amixer", "set", "Master", "mute"] if request.muted else ["amixer", "set", "Master", "unmute"]
    _audio_command(command)
    return _get_volume()


@router.get("/mute", response_model=VolumeInfo, dependencies=[Depends(get_current_user)])
async def mute_audio_get(muted: bool) -> Any:
    """Mute or unmute the master audio channel via query parameter."""
    return await mute_audio(MuteRequest(muted=muted))


@router.get("/devices", response_model=List[AudioDevice], dependencies=[Depends(get_current_user)])
async def audio_devices() -> Any:
    """List available output and input audio devices."""
    sinks = _list_devices(["pactl", "list", "short", "sinks"], ["pactl", "list", "sinks"], "sink")
    sources = _list_devices(["pactl", "list", "short", "sources"], ["pactl", "list", "sources"], "source")
    return sinks + sources


@router.get("/output-devices", response_model=List[AudioDevice], dependencies=[Depends(get_current_user)])
async def audio_output_devices_alias() -> Any:
    """Alias for /audio/devices."""
    return await audio_devices()


@router.post("/beep", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def beep_audio() -> Any:
    """Play a simple notification beep."""
    _play_beep()
    return ActionResponse(success=True, message="beep played")


@router.post("/output-device", response_model=VolumeInfo, dependencies=[Depends(get_current_user)])
async def set_output_device(request: OutputDeviceRequest) -> Any:
    """Switch the default audio output device."""
    _audio_command(["pactl", "set-default-sink", request.device_id])
    return _get_volume()


@router.get("/output-device", response_model=VolumeInfo, dependencies=[Depends(get_current_user)])
async def set_output_device_get(device_id: str) -> Any:
    """Switch the default audio output device via query parameter."""
    return await set_output_device(OutputDeviceRequest(device_id=device_id))
