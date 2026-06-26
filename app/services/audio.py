import re
from pathlib import Path
from typing import Dict, List
from fastapi import  HTTPException

from domain.audio import VolumeInfo, AudioDevice
from utils.run_command import run_command





def parse_volume(output: str) -> VolumeInfo:
    match = re.search(r"\[(\d{1,3})%].*\[(on|off)]", output)
    if not match:
        raise ValueError("could not parse volume")
    return VolumeInfo(volume=int(match.group(1)), muted=(match.group(2) == "off"))


def audio_command(command: List[str]) -> None:
    stdout, stderr, code = run_command(command)
    if code != 0:
        raise HTTPException(status_code=500, detail=stderr or stdout or "audio command failed")


def get_volume() -> VolumeInfo:
    stdout, stderr, code = run_command(["amixer", "get", "Master"])
    if code != 0 or not stdout:
        raise HTTPException(status_code=500, detail=stderr or stdout or "failed to query volume")
    return parse_volume(stdout)


def get_device_descriptions(command: List[str]) -> Dict[str, str]:
    stdout, stderr, code = run_command(command)
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


def friendly_device_name(raw_name: str, description: str = "") -> str:
    if description:
        return description
    cleaned = raw_name
    if "." in cleaned:
        cleaned = cleaned.split(".", 1)[-1]
    cleaned = cleaned.replace("__", " ").replace("_", " ")
    cleaned = cleaned.replace("sink", "").replace("source", "").strip()
    return cleaned or raw_name


def list_devices(command: List[str], desc_command: List[str], dev_type: str) -> List[AudioDevice]:
    descriptions = get_device_descriptions(desc_command)
    stdout, stderr, code = run_command(command)
    if code != 0 or not stdout:
        return []
    devices: List[AudioDevice] = []
    for line in stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            raw_name = parts[1]
            friendly_name = friendly_device_name(raw_name, descriptions.get(raw_name, ""))
            devices.append(AudioDevice(id=parts[0], name=friendly_name, type=dev_type))
    return devices


def play_beep() -> None:
    if Path("/usr/share/sounds/freedesktop/stereo/bell.oga").exists():
        audio_command(["paplay", "/usr/share/sounds/freedesktop/stereo/bell.oga"])
        return

    stdout, stderr, code = run_command(["canberra-gtk-play", "--id", "bell"])
    if code == 0:
        return

    if Path("/usr/share/sounds/alsa/Front_Center.wav").exists():
        audio_command(["aplay", "/usr/share/sounds/alsa/Front_Center.wav"])
        return

    audio_command(["bash", "-lc", "printf '\\a'"])
