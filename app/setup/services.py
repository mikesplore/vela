"""systemd user-service helpers for setup."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def restart_or_start_user_service(service: str) -> None:
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


def write_systemd_units(target_dir: Path) -> tuple[Path, Path]:
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


def enable_services() -> None:
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", "vela.service"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "vela-agent.service"], check=True)


def restart_all_services() -> None:
    for service in ("vela.service", "vela-agent.service"):
        restart_or_start_user_service(service)
