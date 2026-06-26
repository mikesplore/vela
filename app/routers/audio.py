from typing import Any, List
from fastapi import APIRouter, Depends
from app.dependencies import get_current_user
from app.domain.audio import VolumeInfo, ActionResponse, MuteRequest, AudioDevice, \
    OutputDeviceRequest, StepRequest, VolumeRequest
from app.services.audio import get_volume, audio_command, list_devices, play_beep

router = APIRouter(prefix="/audio", tags=["audio"])


@router.get("/volume", response_model=VolumeInfo, dependencies=[Depends(get_current_user)])
async def audio_volume() -> Any:
    """Get current master volume and mute state."""
    return get_volume()


@router.post("/volume", response_model=VolumeInfo, dependencies=[Depends(get_current_user)])
async def set_volume(request: VolumeRequest) -> Any:
    """Set the master volume level."""
    audio_command(["amixer", "set", "Master", f"{request.value}%"])
    return get_volume()


@router.post("/volume/up", response_model=VolumeInfo, dependencies=[Depends(get_current_user)])
async def volume_up(request: StepRequest) -> Any:
    """Increase the master volume by a step."""
    audio_command(["amixer", "set", "Master", f"{request.step}%+"])
    return get_volume()


@router.get("/volume/up", response_model=VolumeInfo, dependencies=[Depends(get_current_user)])
async def volume_up_get(step: int = 5) -> Any:
    """Increase the master volume by a step via query parameter."""
    return await volume_up(StepRequest(step=step))


@router.post("/volume/down", response_model=VolumeInfo, dependencies=[Depends(get_current_user)])
async def volume_down(request: StepRequest) -> Any:
    """Decrease the master volume by a step."""
    audio_command(["amixer", "set", "Master", f"{request.step}%-"])
    return get_volume()


@router.get("/volume/down", response_model=VolumeInfo, dependencies=[Depends(get_current_user)])
async def volume_down_get(step: int = 5) -> Any:
    """Decrease the master volume by a step via query parameter."""
    return await volume_down(StepRequest(step=step))


@router.post("/mute", response_model=VolumeInfo, dependencies=[Depends(get_current_user)])
async def mute_audio(request: MuteRequest) -> Any:
    """Mute or unmute the master audio channel."""
    command = ["amixer", "set", "Master", "mute"] if request.muted else ["amixer", "set", "Master", "unmute"]
    audio_command(command)
    return get_volume()


@router.get("/mute", response_model=VolumeInfo, dependencies=[Depends(get_current_user)])
async def mute_audio_get(muted: bool) -> Any:
    """Mute or unmute the master audio channel via query parameter."""
    return await mute_audio(MuteRequest(muted=muted))


@router.get("/devices", response_model=List[AudioDevice], dependencies=[Depends(get_current_user)])
async def audio_devices() -> Any:
    """List available output and input audio devices."""
    sinks = list_devices(["pactl", "list", "short", "sinks"], ["pactl", "list", "sinks"], "sink")
    sources = list_devices(["pactl", "list", "short", "sources"], ["pactl", "list", "sources"], "source")
    return sinks + sources


@router.get("/output-devices", response_model=List[AudioDevice], dependencies=[Depends(get_current_user)])
async def audio_output_devices_alias() -> Any:
    """Alias for /audio/devices."""
    return await audio_devices()


@router.post("/beep", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def beep_audio() -> Any:
    """Play a simple notification beep."""
    play_beep()
    return ActionResponse(success=True, message="beep played")


@router.post("/output-device", response_model=VolumeInfo, dependencies=[Depends(get_current_user)])
async def set_output_device(request: OutputDeviceRequest) -> Any:
    """Switch the default audio output device."""
    audio_command(["pactl", "set-default-sink", request.device_id])
    return get_volume()


@router.get("/output-device", response_model=VolumeInfo, dependencies=[Depends(get_current_user)])
async def set_output_device_get(device_id: str) -> Any:
    """Switch the default audio output device via query parameter."""
    return await set_output_device(OutputDeviceRequest(device_id=device_id))
