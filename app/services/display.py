import base64
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

from app.domain.display import ResolutionInfo, ScreenshotResponse
from app.services.assistant.images import prepare_client_image_base64
from app.utils.run_command import run_command


def build_screenshot_response(png_bytes: bytes) -> ScreenshotResponse:
    """Return relay-safe base64 for tunnel clients (compresses large PNGs to JPEG)."""
    encoded = base64.b64encode(png_bytes).decode("utf-8")
    prepared, content_type = prepare_client_image_base64(encoded)
    return ScreenshotResponse(image_base64=prepared, content_type=content_type)



def first_connected_output() -> Optional[str]:
    stdout, stderr, code = run_command(["xrandr", "--query"])
    if code != 0 or not stdout:
        return None

    for line in stdout.splitlines():
        if " connected " in line:
            return line.split()[0]
    return None


def parse_current_mode(output: str) -> Optional[Dict[str, Any]]:
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


def get_display_info() -> Optional[ResolutionInfo]:
    stdout, stderr, code = run_command(["xrandr", "--query"])
    if code != 0 or not stdout:
        return None
    current = parse_current_mode(stdout)
    if not current:
        return None
    return ResolutionInfo(
        width=current["width"],
        height=current["height"],
        refresh=current["refresh"],
        output=current["output"],
    )


def get_brightness() -> Optional[float]:
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

    stdout, stderr, code = run_command(["xrandr", "--verbose"])
    if code != 0 or not stdout:
        return None
    match = re.search(r"Brightness:\s*([0-9.]+)", stdout)
    if not match:
        return None
    return float(match.group(1)) * 100.0


def set_brightness_with_backlight(value: int) -> tuple[bool, str]:
    for cmd in (
            ["brightnessctl", "set", f"{value}%"],
            ["light", "-S", str(value)],
            ["xbacklight", "-set", str(value)],
    ):
        stdout, stderr, code = run_command(cmd)
        if code == 0:
            return True, f"brightness set to {value}"
    return False, stderr or stdout or "failed to set brightness"


def run_lock() -> tuple[bool, str]:
    for cmd in [["xdg-screensaver", "lock"], ["loginctl", "lock-session"], ["gnome-screensaver-command", "--lock"]]:
        stdout, stderr, code = run_command(cmd)
        if code == 0:
            return True, "screen locked"
    return False, "screen lock command not found or failed"


def run_night_light(enabled: bool, temperature: Optional[int]) -> tuple[bool, str]:
    stdout, stderr, code = run_command([
        "gsettings",
        "set",
        "org.gnome.settings-daemon.plugins.color",
        "night-light-enabled",
        "true" if enabled else "false",
    ])
    if code != 0:
        return False, stderr or stdout or "failed to toggle night light"
    if temperature is not None:
        stdout, stderr, code = run_command([
            "gsettings",
            "set",
            "org.gnome.settings-daemon.plugins.color",
            "night-light-temperature",
            str(temperature),
        ])
        if code != 0:
            return False, stderr or stdout or "failed to set night light temperature"
    return True, "night light updated"


def set_mutter_power_save_mode(mode: int) -> tuple[bool, str]:
    stdout, stderr, code = run_command([
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


def get_mutter_power_save_mode() -> tuple[Optional[int], str]:
    stdout, stderr, code = run_command([
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


def capture_screenshot_with_flameshot() -> bytes:
    pictures_dir = Path(os.path.expanduser("~/Pictures"))
    pictures_dir.mkdir(parents=True, exist_ok=True)
    before = {path.resolve() for path in pictures_dir.glob("*.png")}
    stdout, stderr, code = run_command(["flameshot", "full", "-p", str(pictures_dir)], timeout=30)
    if code != 0:
        raise RuntimeError(stderr or stdout or "flameshot failed")

    candidates = [path for path in pictures_dir.glob("*.png") if path.resolve() not in before]
    if not candidates:
        candidates = list(pictures_dir.glob("*.png"))
    if not candidates:
        raise RuntimeError("flameshot did not produce a PNG file")

    newest = max(candidates, key=lambda path: path.stat().st_mtime)
    return newest.read_bytes()
