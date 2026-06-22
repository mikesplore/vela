import base64
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.dependencies import get_current_user

router = APIRouter(prefix="/display", tags=["display"])


class ScreenshotResponse(BaseModel):
    image_base64: str


class RecordRequest(BaseModel):
    duration_seconds: int = Field(..., gt=0, le=60)


class BrightnessRequest(BaseModel):
    value: int = Field(..., ge=0, le=100)


class ResolutionRequest(BaseModel):
    width: int = Field(..., gt=0)
    height: int = Field(..., gt=0)
    refresh: int = Field(..., gt=0)


class RotateRequest(BaseModel):
    orientation: str = Field(..., pattern="^(normal|left|right|inverted)$")


class NightLightRequest(BaseModel):
    enabled: bool
    temperature: Optional[int] = Field(None, ge=1000, le=10000)


class ValueResponse(BaseModel):
    success: bool
    message: Optional[str] = None


MUTTER_POWER_SAVE_MODE_ON = 0
MUTTER_POWER_SAVE_MODE_OFF = 1


class PowerSaveState(BaseModel):
    power_save_mode: int
    is_on: bool
    message: str


class BrightnessInfo(BaseModel):
    brightness: Optional[float]


class ResolutionInfo(BaseModel):
    width: int
    height: int
    refresh: Optional[float]
    output: str


def _run_command(cmd: List[str], timeout: int = 10) -> tuple[str, str, int]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        return "", str(exc), 1


def _first_connected_output() -> Optional[str]:
    stdout, stderr, code = _run_command(["xrandr", "--query"])
    if code != 0 or not stdout:
        return None

    for line in stdout.splitlines():
        if " connected " in line:
            return line.split()[0]
    return None


def _parse_current_mode(output: str) -> Optional[Dict[str, Any]]:
    current_output = None
    current_mode = None
    refresh_rate = None

    for line in output.splitlines():
        if " connected " in line:
            current_output = line.split()[0]
            match = re.search(r"(\d+x\d+).*?([0-9.]+)\*", line)
            if match:
                dims = match.group(1)
                refresh_rate = float(match.group(2))
                width, height = map(int, dims.split("x"))
                return {"output": current_output, "width": width, "height": height, "refresh": refresh_rate}
        elif current_output and line.startswith("   "):
            match = re.search(r"(\d+x\d+).*?([0-9.]+)\*", line)
            if match:
                dims = match.group(1)
                refresh_rate = float(match.group(2))
                width, height = map(int, dims.split("x"))
                return {"output": current_output, "width": width, "height": height, "refresh": refresh_rate}
    return None


def _get_display_info() -> Optional[ResolutionInfo]:
    stdout, stderr, code = _run_command(["xrandr", "--query"])
    if code != 0 or not stdout:
        return None
    current = _parse_current_mode(stdout)
    if not current:
        return None
    return ResolutionInfo(
        width=current["width"],
        height=current["height"],
        refresh=current["refresh"],
        output=current["output"],
    )


def _get_brightness() -> Optional[float]:
    backlight_dir = Path("/sys/class/backlight")
    if backlight_dir.exists():
        for device in sorted(backlight_dir.glob("*")):
            brightness_path = device / "brightness"
            max_brightness_path = device / "max_brightness"
            if brightness_path.exists() and max_brightness_path.exists():
                try:
                    current = int(brightness_path.read_text().strip())
                    maximum = int(max_brightness_path.read_text().strip())
                    if maximum > 0:
                        return (current / maximum) * 100.0
                except (OSError, ValueError):
                    continue

    stdout, stderr, code = _run_command(["xrandr", "--verbose"])
    if code != 0 or not stdout:
        return None
    match = re.search(r"Brightness:\s*([0-9.]+)", stdout)
    if not match:
        return None
    return float(match.group(1)) * 100.0


def _set_brightness_with_backlight(value: int) -> tuple[bool, str]:
    for cmd in (
        ["brightnessctl", "set", f"{value}%"],
        ["light", "-S", str(value)],
        ["xbacklight", "-set", str(value)],
    ):
        stdout, stderr, code = _run_command(cmd)
        if code == 0:
            return True, f"brightness set to {value}"
    return False, stderr or stdout or "failed to set brightness"


def _run_lock() -> tuple[bool, str]:
    for cmd in [["xdg-screensaver", "lock"], ["loginctl", "lock-session"], ["gnome-screensaver-command", "--lock"]]:
        stdout, stderr, code = _run_command(cmd)
        if code == 0:
            return True, "screen locked"
    return False, "screen lock command not found or failed"


def _run_night_light(enabled: bool, temperature: Optional[int]) -> tuple[bool, str]:
    stdout, stderr, code = _run_command([
        "gsettings",
        "set",
        "org.gnome.settings-daemon.plugins.color",
        "night-light-enabled",
        "true" if enabled else "false",
    ])
    if code != 0:
        return False, stderr or stdout or "failed to toggle night light"
    if temperature is not None:
        stdout, stderr, code = _run_command([
            "gsettings",
            "set",
            "org.gnome.settings-daemon.plugins.color",
            "night-light-temperature",
            str(temperature),
        ])
        if code != 0:
            return False, stderr or stdout or "failed to set night light temperature"
    return True, "night light updated"


def _set_mutter_power_save_mode(mode: int) -> tuple[bool, str]:
    stdout, stderr, code = _run_command([
        "busctl",
        "--user",
        "set-property",
        "org.gnome.Mutter.DisplayConfig",
        "/org/gnome/Mutter/DisplayConfig",
        "org.gnome.Mutter.DisplayConfig",
        "PowerSaveMode",
        "i",
        str(mode),
    ])
    if code == 0:
        return True, "mutter power save updated"
    return False, stderr or stdout or "failed to set Mutter power save mode"


def _get_mutter_power_save_mode() -> tuple[Optional[int], str]:
    stdout, stderr, code = _run_command([
        "busctl",
        "--user",
        "get-property",
        "org.gnome.Mutter.DisplayConfig",
        "/org/gnome/Mutter/DisplayConfig",
        "org.gnome.Mutter.DisplayConfig",
        "PowerSaveMode",
    ])
    if code != 0 or not stdout:
        return None, stderr or stdout or "failed to read Mutter power save mode"

    match = re.search(r"(-?\d+)", stdout)
    if not match:
        return None, f"unexpected Mutter power save output: {stdout}"
    return int(match.group(1)), "mutter power save state read"


def _capture_screenshot_with_flameshot() -> bytes:
    pictures_dir = Path(os.path.expanduser("~/Pictures"))
    pictures_dir.mkdir(parents=True, exist_ok=True)
    before = {path.resolve() for path in pictures_dir.glob("*.png")}
    stdout, stderr, code = _run_command(["flameshot", "full", "-p", str(pictures_dir)], timeout=30)
    if code != 0:
        raise RuntimeError(stderr or stdout or "flameshot failed")

    candidates = [path for path in pictures_dir.glob("*.png") if path.resolve() not in before]
    if not candidates:
        candidates = list(pictures_dir.glob("*.png"))
    if not candidates:
        raise RuntimeError("flameshot did not produce a PNG file")

    newest = max(candidates, key=lambda path: path.stat().st_mtime)
    return newest.read_bytes()


@router.get("/screenshot", response_model=ScreenshotResponse, dependencies=[Depends(get_current_user)])
async def display_screenshot() -> Any:
    """Capture the current screen and return it as a base64 PNG."""
    try:
        data = _capture_screenshot_with_flameshot()
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
    display_info = _get_display_info()
    if not display_info:
        raise HTTPException(status_code=500, detail="Could not determine display resolution")
    display_name = os.environ.get("DISPLAY", ":0")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
        tmp_path = tmp.name
    try:
        stdout, stderr, code = _run_command([
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
    success, message = _set_mutter_power_save_mode(MUTTER_POWER_SAVE_MODE_OFF)
    if success:
        return ValueResponse(success=True, message="monitor off (mutter)")

    # Try xset DPMS as a fallback (X11)
    stdout, stderr, code = _run_command(["xset", "dpms", "force", "off"])
    if code == 0:
        return ValueResponse(success=True, message="monitor off (xset)")

    # Fallback: try turning off each connected output via xrandr
    display_info = _get_display_info()
    if display_info:
        output = display_info.output
        stdout2, stderr2, code2 = _run_command(["xrandr", "--output", output, "--off"])
        if code2 == 0:
            return ValueResponse(success=True, message=f"monitor off (xrandr:{output})")

    # Fallback: try swaymsg (Wayland compositor using wlroots)
    stdout3, stderr3, code3 = _run_command(["swaymsg", "output", "*", "disable"])
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
    success, message = _set_mutter_power_save_mode(MUTTER_POWER_SAVE_MODE_ON)
    if success:
        return ValueResponse(success=True, message="monitor on (mutter)")

    stdout, stderr, code = _run_command(["xset", "dpms", "force", "on"])
    if code == 0:
        return ValueResponse(success=True, message="monitor on (xset)")

    # If Mutter/xset failed, attempt a generic xrandr re-enable of the first output.
    display_info = _get_display_info()
    if display_info:
        stdout2, stderr2, code2 = _run_command(["xrandr", "--output", display_info.output, "--auto"])
        if code2 == 0:
            return ValueResponse(success=True, message=f"monitor on (xrandr:{display_info.output})")

    stdout3, stderr3, code3 = _run_command(["swaymsg", "output", "*", "enable"])
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
    mode, message = _get_mutter_power_save_mode()
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
    brightness = _get_brightness()
    return BrightnessInfo(brightness=brightness)


@router.post("/brightness", response_model=ValueResponse, dependencies=[Depends(get_current_user)])
async def set_brightness(request: BrightnessRequest) -> Any:
    """Set screen brightness using the first available backlight controller or XRandR fallback."""
    success, message = _set_brightness_with_backlight(request.value)
    if success:
        return ValueResponse(success=True, message=message)

    output = _first_connected_output()
    if output:
        value = request.value / 100.0
        stdout, stderr, code = _run_command(["xrandr", "--output", output, "--brightness", str(value)])
        if code == 0:
            return ValueResponse(success=True, message=f"brightness set to {request.value}")
        last_error = stderr or stdout or "failed to set brightness"
    else:
        last_error = "No connected display found"

    raise HTTPException(status_code=500, detail=last_error)


@router.get("/resolution", response_model=ResolutionInfo, dependencies=[Depends(get_current_user)])
async def display_resolution() -> Any:
    """Get current resolution and refresh rate."""
    info = _get_display_info()
    if not info:
        raise HTTPException(status_code=500, detail="Could not query display settings")
    return info


@router.post("/resolution", response_model=ValueResponse, dependencies=[Depends(get_current_user)])
async def set_resolution(request: ResolutionRequest) -> Any:
    """Set the screen resolution and refresh rate."""
    output = _first_connected_output()
    if not output:
        raise HTTPException(status_code=500, detail="No connected display found")
    stdout, stderr, code = _run_command([
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


def _build_rotate_command(output: str, orientation: str, width: Optional[int] = None, height: Optional[int] = None) -> List[str]:
    cmd = ["xrandr", "--output", output, "--rotate", orientation]
    if orientation in {"left", "right"} and width is not None and height is not None:
        cmd = ["xrandr", "--fb", f"{height}x{width}", "--output", output, "--rotate", orientation]
    return cmd


@router.post("/rotate", response_model=ValueResponse, dependencies=[Depends(get_current_user)])
async def rotate_display(request: RotateRequest) -> Any:
    """Rotate the display orientation."""
    output = _first_connected_output()
    if not output:
        raise HTTPException(status_code=500, detail="No connected display found")

    stdout, stderr, code = _run_command(["xrandr", "--output", output, "--rotate", request.orientation])
    if code != 0:
        if "BadMatch" in stderr or "BadMatch" in stdout:
            info = _get_display_info()
            if info and request.orientation in {"left", "right"}:
                fallback_cmd = _build_rotate_command(output, request.orientation, info.width, info.height)
                stdout2, stderr2, code2 = _run_command(fallback_cmd)
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
    success, message = _run_lock()
    if not success:
        raise HTTPException(status_code=500, detail=message)
    return ValueResponse(success=True, message=message)


@router.post("/night-light", response_model=ValueResponse, dependencies=[Depends(get_current_user)])
async def night_light(request: NightLightRequest) -> Any:
    """Enable or disable night light and optionally set temperature."""
    success, message = _run_night_light(request.enabled, request.temperature)
    if not success:
        raise HTTPException(status_code=500, detail=message)
    return ValueResponse(success=True, message=message)
