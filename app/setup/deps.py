"""System dependency detection and optional package install."""

from __future__ import annotations

import shutil
import subprocess


DEPENDENCY_GROUPS = [
    {
        "feature": "Filesystem",
        "description": "Open files and paths from API calls.",
        "commands": ["xdg-open"],
        "packages": {"apt": ["xdg-utils"], "dnf": ["xdg-utils"], "pacman": ["xdg-utils"]},
    },
    {
        "feature": "Audio",
        "description": "Adjust volume/output and play sounds.",
        "commands": ["amixer", "pactl"],
        "packages": {
            "apt": ["alsa-utils", "pulseaudio-utils"],
            "dnf": ["alsa-utils", "pulseaudio-utils"],
            "pacman": ["alsa-utils", "pulseaudio-utils"],
        },
    },
    {
        "feature": "Display/Screenshot",
        "description": "Manage display state and capture screenshots.",
        "commands": ["xrandr", "flameshot", "xset", "ffmpeg", "busctl", "brightnessctl", "gsettings"],
        "packages": {
            "apt": ["x11-xserver-utils", "flameshot", "ffmpeg", "libglib2.0-bin", "brightnessctl", "systemd"],
            "dnf": ["xorg-xrandr", "flameshot", "xorg-xset", "ffmpeg", "glib2", "brightnessctl", "systemd"],
            "pacman": ["xorg-xrandr", "flameshot", "xorg-xset", "ffmpeg", "glib2", "brightnessctl", "systemd"],
        },
    },
    {
        "feature": "Input Control",
        "description": "Mouse/keyboard actions and window introspection.",
        "commands": ["xdotool", "xprop", "xwininfo"],
        "packages": {
            "apt": ["xdotool", "x11-utils"],
            "dnf": ["xdotool", "xorg-xprop", "xorg-xwininfo"],
            "pacman": ["xdotool", "xorg-xprop", "xorg-xwininfo"],
        },
    },
    {
        "feature": "Media",
        "description": "Control media playback sessions.",
        "commands": ["playerctl"],
        "packages": {"apt": ["playerctl"], "dnf": ["playerctl"], "pacman": ["playerctl"]},
    },
    {
        "feature": "Network",
        "description": "Inspect/manage network, bluetooth, and connectivity tests.",
        "commands": ["nmcli", "bluetoothctl", "rfkill", "ping"],
        "packages": {
            "apt": ["network-manager", "bluez", "util-linux", "iputils-ping"],
            "dnf": ["NetworkManager", "bluez", "util-linux", "iputils"],
            "pacman": ["networkmanager", "bluez", "util-linux", "iputils"],
        },
    },
    {
        "feature": "Notifications",
        "description": "Send desktop notifications.",
        "commands": ["notify-send"],
        "packages": {"apt": ["libnotify-bin"], "dnf": ["libnotify"], "pacman": ["libnotify"]},
    },
    {
        "feature": "Clipboard",
        "description": "Read and write the desktop clipboard.",
        "commands": ["xclip", "wl-copy"],
        "packages": {
            "apt": ["xclip", "wl-clipboard"],
            "dnf": ["xclip", "wl-clipboard"],
            "pacman": ["xclip", "wl-clipboard"],
        },
    },
    {
        "feature": "Power",
        "description": "Power actions and profile controls.",
        "commands": ["systemctl", "powerprofilesctl"],
        "packages": {
            "apt": ["systemd", "power-profiles-daemon"],
            "dnf": ["systemd", "power-profiles-daemon"],
            "pacman": ["systemd", "power-profiles-daemon"],
        },
    },
    {
        "feature": "Security",
        "description": "Lock/session and webcam security operations.",
        "commands": ["loginctl", "modprobe", "pactl", "pkill", "who", "ffmpeg"],
        "packages": {
            "apt": ["systemd", "kmod", "pulseaudio-utils", "procps", "util-linux", "coreutils", "ffmpeg"],
            "dnf": ["systemd", "kmod", "pulseaudio-utils", "procps-ng", "util-linux", "coreutils", "ffmpeg"],
            "pacman": ["systemd", "kmod", "pulseaudio-utils", "procps-ng", "util-linux", "coreutils", "ffmpeg"],
        },
    },
    {
        "feature": "System Info",
        "description": "Read hardware/system inventory.",
        "commands": ["lspci", "lsusb", "dmidecode", "xrandr"],
        "packages": {
            "apt": ["pciutils", "usbutils", "dmidecode", "x11-xserver-utils"],
            "dnf": ["pciutils", "usbutils", "dmidecode", "xorg-xrandr"],
            "pacman": ["pciutils", "usbutils", "dmidecode", "xorg-xrandr"],
        },
    },
    {
        "feature": "Maintenance",
        "description": "Inspect service logs and time state.",
        "commands": ["journalctl", "systemctl", "timedatectl"],
        "packages": {"apt": ["systemd"], "dnf": ["systemd"], "pacman": ["systemd"]},
    },
]


def detect_pkg_manager() -> str:
    if shutil.which("apt-get"):
        return "apt"
    if shutil.which("dnf"):
        return "dnf"
    if shutil.which("pacman"):
        return "pacman"
    return "unknown"


def check_missing_dependencies() -> list[dict]:
    missing = []
    for group in DEPENDENCY_GROUPS:
        missing_commands = [cmd for cmd in group["commands"] if not shutil.which(cmd)]
        if missing_commands:
            missing.append({**group, "missing_commands": missing_commands})
    return missing


def install_packages(pkg_manager: str, packages: list[str]) -> None:
    if pkg_manager == "apt":
        subprocess.run(["sudo", "apt-get", "update"], check=True)
        subprocess.run(["sudo", "apt-get", "install", "-y", *packages], check=True)
        return
    if pkg_manager == "dnf":
        subprocess.run(["sudo", "dnf", "install", "-y", *packages], check=True)
        return
    if pkg_manager == "pacman":
        subprocess.run(["sudo", "pacman", "-S", "--needed", "--noconfirm", *packages], check=True)
        return
    raise RuntimeError(f"Unsupported package manager: {pkg_manager}")


def dependency_install_plan() -> tuple[list[dict], str, list[str]]:
    """Return missing dependency groups and the packages that can satisfy them."""
    missing = check_missing_dependencies()
    pkg_manager = detect_pkg_manager()
    packages = sorted(
        {pkg for group in missing for pkg in group["packages"].get(pkg_manager, [])}
    )
    return missing, pkg_manager, packages


def check_and_offer_dependency_install(prompt_fn) -> None:
    print("")
    print("Checking system dependencies...")
    missing, pkg_manager, packages = dependency_install_plan()
    if not missing:
        print("All checked runtime tools are already available.")
        return

    print("Missing tools detected:")
    for group in missing:
        print(f"- {group['feature']}")
        print(f"  What it does: {group['description']}")
        print(f"  Missing commands: {', '.join(group['missing_commands'])}")

    install_now = prompt_fn("N", "Install missing packages now? [y/N]").lower()
    if install_now not in {"y", "yes"}:
        print("Skipping package install. Missing features may fail until tools are installed.")
        return

    if pkg_manager == "unknown":
        print("No supported package manager detected (apt, dnf, pacman). Install tools manually.")
        return

    if not packages:
        print("No package suggestions available for the detected missing commands.")
        return

    print(f"Installing packages via {pkg_manager}: {' '.join(packages)}")
    install_packages(pkg_manager, packages)
    print("Dependency installation step completed.")
