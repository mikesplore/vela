import base64
import os
import re
import subprocess
import tempfile
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dependencies import get_current_user

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
    stdout, stderr, code = _run_command(["xrandr", "--verbose"])
    if code != 0 or not stdout:
        return None
    match = re.search(r"Brightness:\s*([0-9.]+)", stdout)
    if not match:
        return None
    return float(match.group(1)) * 100.0


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


def _capture_screenshot_with_gnome_screenshot() -> bytes:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
        tmp_path = tmp.name
    try:
        stdout, stderr, code = _run_command(["gnome-screenshot", "-f", tmp_path], timeout=30)
        if code != 0:
            raise RuntimeError(stderr or stdout or "gnome-screenshot failed")
        with open(tmp_path, "rb") as fh:
            return fh.read()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _capture_screenshot_with_scrot() -> bytes:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
        tmp_path = tmp.name
    try:
        stdout, stderr, code = _run_command(["scrot", tmp_path])
        if code != 0:
            raise RuntimeError(stderr or stdout or "scrot failed")
        with open(tmp_path, "rb") as fh:
            return fh.read()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _capture_screenshot_with_x11() -> bytes:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
        tmp_path = tmp.name
    try:
        stdout, stderr, code = _run_command(["import", "-window", "root", tmp_path])
        if code != 0:
            raise RuntimeError(stderr or stdout or "import screenshot failed")
        with open(tmp_path, "rb") as fh:
            return fh.read()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@router.get("/screenshot", response_model=ScreenshotResponse, dependencies=[Depends(get_current_user)])
async def display_screenshot() -> Any:
    """Capture the current screen and return it as a base64 PNG."""
    try:
        data = _capture_screenshot_with_gnome_screenshot()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Screenshot capture failed using gnome-screenshot. Install gnome-screenshot and ensure it is available in PATH. "
                "Error: " + str(exc)
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
    """Turn the monitor off using DPMS."""
    stdout, stderr, code = _run_command(["xset", "dpms", "force", "off"])
    if code != 0:
        raise HTTPException(status_code=500, detail=stderr or stdout or "failed to turn off monitor")
    return ValueResponse(success=True, message="monitor off")


@router.post("/monitor/on", response_model=ValueResponse, dependencies=[Depends(get_current_user)])
async def monitor_on() -> Any:
    """Turn the monitor on using DPMS."""
    stdout, stderr, code = _run_command(["xset", "dpms", "force", "on"])
    if code != 0:
        raise HTTPException(status_code=500, detail=stderr or stdout or "failed to turn on monitor")
    return ValueResponse(success=True, message="monitor on")


@router.get("/brightness", response_model=BrightnessInfo, dependencies=[Depends(get_current_user)])
async def display_brightness() -> Any:
    """Get the current screen brightness."""
    brightness = _get_brightness()
    return BrightnessInfo(brightness=brightness)


@router.post("/brightness", response_model=ValueResponse, dependencies=[Depends(get_current_user)])
async def set_brightness(request: BrightnessRequest) -> Any:
    """Set screen brightness using xrandr."""
    output = _first_connected_output()
    if not output:
        raise HTTPException(status_code=500, detail="No connected display found")
    value = request.value / 100.0
    stdout, stderr, code = _run_command(["xrandr", "--output", output, "--brightness", str(value)])
    if code != 0:
        raise HTTPException(status_code=500, detail=stderr or stdout or "failed to set brightness")
    return ValueResponse(success=True, message=f"brightness set to {request.value}")


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
