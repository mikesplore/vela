import base64
import os
import tempfile
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from app.dependencies import get_current_user
from domain.display import ScreenshotResponse, RecordRequest, MUTTER_POWER_SAVE_MODE_OFF, ValueResponse, \
    MUTTER_POWER_SAVE_MODE_ON, PowerSaveState, BrightnessInfo, BrightnessRequest, ResolutionInfo, ResolutionRequest, \
    RotateRequest, NightLightRequest
from services.display import capture_screenshot_with_flameshot, get_display_info, set_mutter_power_save_mode, \
    get_mutter_power_save_mode, get_brightness, set_brightness_with_backlight, first_connected_output, run_lock, \
    run_night_light
from utils.run_command import run_command

router = APIRouter(prefix="/display", tags=["display"])


@router.get("/screenshot", response_model=ScreenshotResponse, dependencies=[Depends(get_current_user)])
async def display_screenshot() -> Any:
    """Capture the current screen and return it as a base64 PNG."""
    try:
        data = capture_screenshot_with_flameshot()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                    "Screenshot capture failed using flameshot. "
                    "Make sure the backend is started from the graphical desktop session so DISPLAY/WAYLAND_DISPLAY, XAUTHORITY, and DBUS_SESSION_BUS_ADDRESS are available. "
                    + str(exc)
            ),
        )
    encoded = base64.b64encode(data).decode("utf-8")
    return ScreenshotResponse(image_base64=encoded)


@router.post("/record", response_model=ScreenshotResponse, dependencies=[Depends(get_current_user)])
async def display_record(request: RecordRequest) -> Any:
    """Record a short screen clip and return it as a base64 MP4."""
    display_info = get_display_info()
    if not display_info:
        raise HTTPException(status_code=500, detail="Could not determine display resolution")
    display_name = os.environ.get("DISPLAY", ":0")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
        tmp_path = tmp.name
    try:
        stdout, stderr, code = run_command([
            "ffmpeg",
            "-y",
            "-video_size",
            f"{display_info.width}x{display_info.height}",
            "-framerate",
            "15",
            "-f",
            "x11grab",
            "-i",
            display_name,
            "-t",
            str(request.duration_seconds),
            tmp_path,
        ])
        if code != 0:
            raise HTTPException(status_code=500, detail=stderr or stdout or "ffmpeg failed")
        with open(tmp_path, "rb") as fh:
            encoded = base64.b64encode(fh.read()).decode("utf-8")
        return ScreenshotResponse(image_base64=encoded)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@router.post("/monitor/off", response_model=ValueResponse, dependencies=[Depends(get_current_user)])
async def monitor_off() -> Any:
    """Turn the monitor off using Mutter power save mode, with fallbacks."""
    success, message = set_mutter_power_save_mode(MUTTER_POWER_SAVE_MODE_OFF)
    if success:
        return ValueResponse(success=True, message="monitor off (mutter)")

    # Try xset DPMS as a fallback (X11)
    stdout, stderr, code = run_command(["xset", "dpms", "force", "off"])
    if code == 0:
        return ValueResponse(success=True, message="monitor off (xset)")

    # Fallback: try turning off each connected output via xrandr
    display_info = get_display_info()
    if display_info:
        output = display_info.output
        stdout2, stderr2, code2 = run_command(["xrandr", "--output", output, "--off"])
        if code2 == 0:
            return ValueResponse(success=True, message=f"monitor off (xrandr:{output})")

    # Fallback: try swaymsg (Wayland compositor using wlroots)
    stdout3, stderr3, code3 = run_command(["swaymsg", "output", "*", "disable"])
    if code3 == 0:
        return ValueResponse(success=True, message="monitor off (swaymsg)")

    # If all attempts failed, return aggregated error for debugging
    details = "; ".join(
        filter(
            None,
            [message, stderr, stderr2 if 'stderr2' in locals() else None, stderr3 if 'stderr3' in locals() else None],
        )
    )
    raise HTTPException(status_code=500, detail=details or stdout or "failed to turn off monitor")


@router.post("/monitor/on", response_model=ValueResponse, dependencies=[Depends(get_current_user)])
async def monitor_on() -> Any:
    """Turn the monitor on using Mutter power save mode, with fallbacks."""
    success, message = set_mutter_power_save_mode(MUTTER_POWER_SAVE_MODE_ON)
    if success:
        return ValueResponse(success=True, message="monitor on (mutter)")

    stdout, stderr, code = run_command(["xset", "dpms", "force", "on"])
    if code == 0:
        return ValueResponse(success=True, message="monitor on (xset)")

    # If Mutter/xset failed, attempt a generic xrandr re-enable of the first output.
    display_info = get_display_info()
    if display_info:
        stdout2, stderr2, code2 = run_command(["xrandr", "--output", display_info.output, "--auto"])
        if code2 == 0:
            return ValueResponse(success=True, message=f"monitor on (xrandr:{display_info.output})")

    stdout3, stderr3, code3 = run_command(["swaymsg", "output", "*", "enable"])
    if code3 == 0:
        return ValueResponse(success=True, message="monitor on (swaymsg)")

    details = "; ".join(
        filter(
            None,
            [message, stderr, stderr2 if 'stderr2' in locals() else None, stderr3 if 'stderr3' in locals() else None],
        )
    )
    raise HTTPException(status_code=500, detail=details or stdout or "failed to turn on monitor")


@router.get("/monitor/state", response_model=PowerSaveState, dependencies=[Depends(get_current_user)])
async def monitor_state() -> Any:
    """Read the current Mutter power-save state so the agent can see whether the screen is on."""
    mode, message = get_mutter_power_save_mode()
    if mode is None:
        raise HTTPException(status_code=500, detail=message)
    return PowerSaveState(
        power_save_mode=mode,
        is_on=mode == MUTTER_POWER_SAVE_MODE_ON,
        message=message,
    )


@router.get("/brightness", response_model=BrightnessInfo, dependencies=[Depends(get_current_user)])
async def display_brightness() -> Any:
    """Get the current screen brightness."""
    brightness = get_brightness()
    return BrightnessInfo(brightness=brightness)


@router.post("/brightness", response_model=ValueResponse, dependencies=[Depends(get_current_user)])
async def set_brightness(request: BrightnessRequest) -> Any:
    """Set screen brightness using the first available backlight controller or XRandR fallback."""
    success, message = set_brightness_with_backlight(request.value)
    if success:
        return ValueResponse(success=True, message=message)

    output = first_connected_output()
    if output:
        value = request.value / 100.0
        stdout, stderr, code = run_command(["xrandr", "--output", output, "--brightness", str(value)])
        if code == 0:
            return ValueResponse(success=True, message=f"brightness set to {request.value}")
        last_error = stderr or stdout or "failed to set brightness"
    else:
        last_error = "No connected display found"

    raise HTTPException(status_code=500, detail=last_error)


@router.get("/resolution", response_model=ResolutionInfo, dependencies=[Depends(get_current_user)])
async def display_resolution() -> Any:
    """Get current resolution and refresh rate."""
    info = get_display_info()
    if not info:
        raise HTTPException(status_code=500, detail="Could not query display settings")
    return info


@router.post("/resolution", response_model=ValueResponse, dependencies=[Depends(get_current_user)])
async def set_resolution(request: ResolutionRequest) -> Any:
    """Set the screen resolution and refresh rate."""
    output = first_connected_output()
    if not output:
        raise HTTPException(status_code=500, detail="No connected display found")
    stdout, stderr, code = run_command([
        "xrandr",
        "--output",
        output,
        "--mode",
        f"{request.width}x{request.height}",
        "--rate",
        str(request.refresh),
    ])
    if code != 0:
        raise HTTPException(status_code=500, detail=stderr or stdout or "failed to set resolution")
    return ValueResponse(success=True, message="resolution updated")


def _build_rotate_command(output: str, orientation: str, width: Optional[int] = None, height: Optional[int] = None) -> \
List[str]:
    cmd = ["xrandr", "--output", output, "--rotate", orientation]
    if orientation in {"left", "right"} and width is not None and height is not None:
        cmd = ["xrandr", "--fb", f"{height}x{width}", "--output", output, "--rotate", orientation]
    return cmd


@router.post("/rotate", response_model=ValueResponse, dependencies=[Depends(get_current_user)])
async def rotate_display(request: RotateRequest) -> Any:
    """Rotate the display orientation."""
    output = first_connected_output()
    if not output:
        raise HTTPException(status_code=500, detail="No connected display found")

    stdout, stderr, code = run_command(["xrandr", "--output", output, "--rotate", request.orientation])
    if code != 0:
        if "BadMatch" in stderr or "BadMatch" in stdout:
            info = get_display_info()
            if info and request.orientation in {"left", "right"}:
                fallback_cmd = _build_rotate_command(output, request.orientation, info.width, info.height)
                stdout2, stderr2, code2 = run_command(fallback_cmd)
                if code2 == 0:
                    return ValueResponse(success=True, message=f"orientation set to {request.orientation}")
                stderr = stderr2 or stdout2 or stderr
        raise HTTPException(status_code=500, detail=stderr or stdout or "failed to rotate display")
    return ValueResponse(success=True, message=f"orientation set to {request.orientation}")


@router.get("/rotate", response_model=ValueResponse, dependencies=[Depends(get_current_user)])
async def rotate_display_get(orientation: str) -> Any:
    """Rotate the display orientation via query parameter."""
    return await rotate_display(RotateRequest(orientation=orientation))


@router.post("/lock", response_model=ValueResponse, dependencies=[Depends(get_current_user)])
async def lock_screen() -> Any:
    """Lock the current session."""
    success, message = run_lock()
    if not success:
        raise HTTPException(status_code=500, detail=message)
    return ValueResponse(success=True, message=message)


@router.post("/night-light", response_model=ValueResponse, dependencies=[Depends(get_current_user)])
async def night_light(request: NightLightRequest) -> Any:
    """Enable or disable night light and optionally set temperature."""
    success, message = run_night_light(request.enabled, request.temperature)
    if not success:
        raise HTTPException(status_code=500, detail=message)
    return ValueResponse(success=True, message=message)
