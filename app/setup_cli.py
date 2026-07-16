import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import bcrypt
import requests
import yaml

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


def _detect_pkg_manager() -> str:
    if shutil.which("apt-get"):
        return "apt"
    if shutil.which("dnf"):
        return "dnf"
    if shutil.which("pacman"):
        return "pacman"
    return "unknown"


def _check_missing_dependencies() -> list[dict]:
    missing = []
    for group in DEPENDENCY_GROUPS:
        missing_commands = [cmd for cmd in group["commands"] if not shutil.which(cmd)]
        if missing_commands:
            missing.append({**group, "missing_commands": missing_commands})
    return missing


def _install_packages(pkg_manager: str, packages: list[str]) -> None:
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


def _check_and_offer_dependency_install() -> None:
    print("")
    print("Checking system dependencies...")
    missing = _check_missing_dependencies()
    if not missing:
        print("All checked runtime tools are already available.")
        return

    print("Missing tools detected:")
    for group in missing:
        print(f"- {group['feature']}")
        print(f"  What it does: {group['description']}")
        print(f"  Missing commands: {', '.join(group['missing_commands'])}")

    install_now = _prompt("N", "Install missing packages now? [y/N]").lower()
    if install_now not in {"y", "yes"}:
        print("Skipping package install. Missing features may fail until tools are installed.")
        return

    pkg_manager = _detect_pkg_manager()
    if pkg_manager == "unknown":
        print("No supported package manager detected (apt, dnf, pacman). Install tools manually.")
        return

    packages = sorted(
        {
            pkg
            for group in missing
            for pkg in group["packages"].get(pkg_manager, [])
        }
    )
    if not packages:
        print("No package suggestions available for the detected missing commands.")
        return

    print(f"Installing packages via {pkg_manager}: {' '.join(packages)}")
    _install_packages(pkg_manager, packages)
    print("Dependency installation step completed.")


def _prompt(default: str | None, label: str, required: bool = True) -> str:
    while True:
        suffix = f" [{default}]" if default else ""
        value = input(f"{label}{suffix}: ").strip()
        if not value and default is not None:
            value = default
        if value or not required:
            return value
        print(f"{label} is required.")


def _prompt_secret(label: str) -> str:
    import getpass

    while True:
        first = getpass.getpass(f"{label}: ").strip()
        if not first:
            print(f"{label} is required.")
            continue
        second = getpass.getpass("Confirm password: ").strip()
        if first == second:
            return first
        print("Passwords do not match.")


def _normalize_vps_url(raw: str) -> str:
    parsed = urlparse(raw.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("VPS URL must include http:// or https:// and a host")
    return raw.rstrip("/")


def _verify_vps_health(vps_url: str) -> None:
    health_url = f"{vps_url.rstrip('/')}/health"
    print(f"Checking VPS at {health_url} ...")
    resp = requests.get(health_url, timeout=10)
    if resp.status_code != 200:
        raise RuntimeError(f"VPS health check failed: HTTP {resp.status_code} {resp.text}")
    payload = resp.json()
    if payload.get("status") != "ok":
        raise RuntimeError(f"VPS health payload unexpected: {payload}")


def _write_config_yaml(target_dir: Path, username: str, password: str, server_host: str, server_port: int, allowed_dirs: list[str], assistant_pin: str) -> Path:
    config_path = target_dir / "config.yaml"
    config = {
        "host": server_host,
        "port": server_port,
        "secret_key": secrets.token_urlsafe(32),
        "token_expire_minutes": 1440,
        "allowed_origins": [],
        "allowed_base_dirs": allowed_dirs,
        "rate_limit_default": "100/minute",
        "route_rate_limits": {"/auth/token": "10/minute", "/ping": "60/minute"},
        "feature_flags": {
            "display": True,
            "audio": True,
            "power": True,
            "notifications": True,
            "network": True,
            "filesystem": True,
            "input_control": True,
            "system_info": True,
            "monitoring": True,
            "processes": True,
            "security": True,
            "scheduler": True,
            "maintenance": True,
            "media": True,
            "clipboard": True,
        },
        "username": username,
        "password_hash": bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
        "log_level": "INFO",
    }
    if assistant_pin:
        config["assistant_action_pin"] = assistant_pin
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return config_path


def _write_env_file(
    target_dir: Path,
    username: str,
    password: str,
    vps_url: str,
    agent_label: str,
    existing_agent_id: str,
    server_port: int,
    assistant_pin: str,
    existing_secret: str,
) -> Path:
    env_path = target_dir / ".env"
    lines = [
        f"USERNAME={username}",
        f"PASSWORD={password}",
        f"LOCAL_SERVICE_USERNAME={username}",
        f"LOCAL_SERVICE_PASSWORD={password}",
        f"LOCAL_SERVICE_URL=http://127.0.0.1:{server_port}",
        "LOCAL_SERVICE_TOKEN_PATH=/auth/token",
        "LOCAL_SERVICE_AUTH_TOKEN=",
        "LOCAL_SERVICE_AUTH_TOKEN_EXPIRES=",
        f"VPS_URL={vps_url}",
        f"AGENT_NAME={agent_label}",
        f"AGENT_ID={existing_agent_id}",
        f"AGENT_SECRET={existing_secret}",
        "AGENT_CREDENTIAL=",
        "RELAY_SECRET=",
        f"ASSISTANT_ACTION_PIN={assistant_pin}",
        "FIREWORKS_API_KEY=paste_your_key_here",
        "VELA_ASSISTANT_ENABLE_THINKING=false",
        "VELA_FIREWORKS_API_URL=https://api.fireworks.ai/inference/v1",
        "VELA_FIREWORKS_MODEL=accounts/fireworks/models/qwen3p7-plus",
        "RECIPIENT_EMAIL=your_personal_email",
        "RESEND_API_KEY=your_resend_api_key",
        "RESEND_FROM_EMAIL=your_resend_email",
        "SPOTIFY_CLIENT_ID=your_spotify_client_id_here",
        "SPOTIFY_CLIENT_SECRET=your_spotify_client_secret_here",
        f"SPOTIFY_REDIRECT_URI={vps_url}/relay/{existing_agent_id or 'your_agent_id_after_pairing'}/callback",
    ]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(env_path, 0o600)
    return env_path


def _write_systemd_units(target_dir: Path) -> tuple[Path, Path]:
    service_dir = Path.home() / ".config" / "systemd" / "user"
    service_dir.mkdir(parents=True, exist_ok=True)
    desktop_env_file = Path.home() / ".config" / "vela" / "desktop.env"
    desktop_env_file.parent.mkdir(parents=True, exist_ok=True)
    desktop_env_file.write_text(
        "\n".join(
            [
                f"DISPLAY={os.getenv('DISPLAY', '')}",
                f"WAYLAND_DISPLAY={os.getenv('WAYLAND_DISPLAY', '')}",
                f"XAUTHORITY={os.getenv('XAUTHORITY', '')}",
                f"DBUS_SESSION_BUS_ADDRESS={os.getenv('DBUS_SESSION_BUS_ADDRESS', '')}",
                f"XDG_RUNTIME_DIR={os.getenv('XDG_RUNTIME_DIR', '')}",
                f"XDG_SESSION_TYPE={os.getenv('XDG_SESSION_TYPE', '')}",
                f"XDG_CURRENT_DESKTOP={os.getenv('XDG_CURRENT_DESKTOP', '')}",
                f"DESKTOP_SESSION={os.getenv('DESKTOP_SESSION', '')}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    os.chmod(desktop_env_file, 0o600)

    vela_exec = shutil.which("vela") or sys.executable + " -m app.main"
    agent_exec = shutil.which("vela-agent") or sys.executable + " -m app.agent.agent"

    vela_service = service_dir / "vela.service"
    vela_service.write_text(
        f"""[Unit]
Description=Vela RemotePC API
After=network.target

[Service]
Type=simple
WorkingDirectory={target_dir}
Environment=START_AGENT=false
EnvironmentFile={desktop_env_file}
ExecStart={vela_exec}
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
""",
        encoding="utf-8",
    )

    agent_service = service_dir / "vela-agent.service"
    agent_service.write_text(
        f"""[Unit]
Description=Vela RemotePC Agent Tunnel
After=network.target

[Service]
Type=simple
WorkingDirectory={target_dir}
EnvironmentFile={target_dir / '.env'}
ExecStart={agent_exec}
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
""",
        encoding="utf-8",
    )

    return vela_service, agent_service


def _restart_or_start_user_service(service: str) -> None:
    active = subprocess.run(
        ["systemctl", "--user", "is-active", service],
        check=False,
        capture_output=True,
        text=True,
    )
    if (active.stdout or "").strip() == "active":
        subprocess.run(["systemctl", "--user", "restart", service], check=True)
    else:
        subprocess.run(["systemctl", "--user", "start", service], check=True)


def run_setup() -> None:
    target_dir = Path.cwd()
    print("Vela setup")
    print(f"Target directory: {target_dir}")

    username_default = os.getenv("USERNAME") or os.getenv("USER") or "admin"
    username = _prompt(username_default, "Username")
    password = _prompt_secret("Password")

    raw_vps = _prompt(os.getenv("VPS_URL") or "https://vela.mikesplore.tech", "VPS URL")
    if raw_vps and not raw_vps.startswith(("http://", "https://")):
        raw_vps = f"https://{raw_vps}"
    vps_url = _normalize_vps_url(raw_vps)

    agent_label_default = os.getenv("AGENT_NAME") or os.uname().nodename
    agent_label = _prompt(agent_label_default, "Agent label (shown in app)")
    existing_agent_id = (os.getenv("AGENT_ID") or "").strip()
    if not existing_agent_id.startswith("agt_"):
        existing_agent_id = ""

    host = _prompt("127.0.0.1", "Bind host")
    port = int(_prompt("8765", "Port"))
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("Bind host must be localhost-only for safety")

    allowed_dirs_csv = _prompt(str(Path.home()), "Allowed base dirs (comma-separated)")
    allowed_dirs = [str(Path(p.strip()).expanduser()) for p in allowed_dirs_csv.split(",") if p.strip()]
    for path in allowed_dirs:
        if not Path(path).is_absolute():
            raise RuntimeError(f"Allowed directory must be absolute: {path}")

    _check_and_offer_dependency_install()

    assistant_pin = _prompt("", "Assistant action PIN (optional)", required=False)
    existing_secret = ""
    if os.getenv("AGENT_SECRET"):
        reuse = _prompt("N", "Reuse existing agent credential? [y/N]").lower()
        if reuse in {"y", "yes"}:
            existing_secret = os.getenv("AGENT_SECRET", "")

    _verify_vps_health(vps_url)
    config_path = _write_config_yaml(target_dir, username, password, host, port, allowed_dirs, assistant_pin)
    env_path = _write_env_file(
        target_dir,
        username,
        password,
        vps_url,
        agent_label,
        existing_agent_id,
        port,
        assistant_pin,
        existing_secret,
    )
    vela_service, agent_service = _write_systemd_units(target_dir)

    try:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", "--now", "vela.service"], check=True)
        subprocess.run(["systemctl", "--user", "enable", "vela-agent.service"], check=True)
    except Exception as exc:
        print(f"systemd setup warning: {exc}")

    if existing_secret:
        try:
            _restart_or_start_user_service("vela-agent.service")
        except Exception as exc:
            print(f"could not start agent service: {exc}")
    else:
        # Launch pairing immediately for first-time setup.
        subprocess.run([sys.executable, "-m", "app.main", "--pair"], check=False)
        try:
            _restart_or_start_user_service("vela-agent.service")
        except Exception as exc:
            print(f"could not start agent service: {exc}")

    print("")
    print("Setup complete")
    print(f"config: {config_path}")
    print(f"env:    {env_path}")
    print(f"vela service: {vela_service}")
    print(f"agent service: {agent_service}")
