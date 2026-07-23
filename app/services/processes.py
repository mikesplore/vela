"""Process helpers for Vela."""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass

import psutil

from app.utils.desktop_env import ensure_desktop_env


@dataclass
class LaunchResult:
    pid: int | None
    message: str
    detached: bool


def kill_processes_by_name(name: str) -> int:
    killed_count = 0
    for proc in psutil.process_iter(["name"]):
        try:
            if proc.info.get("name") and proc.info["name"].lower() == name.lower():
                proc.terminate()
                proc.wait(timeout=3)
                killed_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
            continue
    return killed_count


def is_process_running(name: str) -> tuple[bool, int, list[int]]:
    """Return whether any process matches the given name (case-insensitive)."""
    pids: list[int] = []
    needle = name.lower()
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            proc_name = proc.info.get("name")
            if proc_name and proc_name.lower() == needle:
                pids.append(int(proc.info["pid"]))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return bool(pids), len(pids), pids


def spawn_detached(argv: list[str]) -> LaunchResult:
    """Launch a process outside the vela.service cgroup when possible.

    Children started with plain ``Popen`` stay in Vela's systemd cgroup, so
    ``systemctl --user stop/restart vela`` kills them. Prefer a transient
    user service via ``systemd-run --no-block`` so desktop apps outlive the API.
    """
    if not argv or not argv[0]:
        raise ValueError("Command is required")

    ensure_desktop_env()
    env = os.environ.copy()

    systemd_run = shutil.which("systemd-run")
    if systemd_run:
        unit = f"vela-app-{uuid.uuid4().hex[:10]}"
        # Use a transient .service (not --scope): scope mode waits until the
        # command exits, which would block the API on long-lived GUI apps.
        cmd = [
            systemd_run,
            "--user",
            "--collect",
            "--no-block",
            "--same-dir",
            f"--unit={unit}",
        ]
        for key in (
            "DISPLAY",
            "WAYLAND_DISPLAY",
            "XAUTHORITY",
            "DBUS_SESSION_BUS_ADDRESS",
            "XDG_RUNTIME_DIR",
            "XDG_SESSION_TYPE",
            "XDG_CURRENT_DESKTOP",
            "DESKTOP_SESSION",
        ):
            if env.get(key):
                cmd.append(f"--setenv={key}={env[key]}")
        cmd.extend(["--", *argv])
        completed = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False, timeout=10)
        if completed.returncode == 0:
            pid = _unit_main_pid(unit)
            return LaunchResult(
                pid=pid,
                message=f"Launched detached from Vela service (unit {unit}.service).",
                detached=True,
            )
        # Fall through if systemd-run rejected the command (e.g. missing binary).
        # Keep stderr available for debugging rare failures.
        if completed.stderr:
            import logging

            logging.getLogger(__name__).debug("systemd-run failed: %s", completed.stderr.strip())

    # Fallback: new session. Survives Vela stop when KillMode=process on vela.service.
    try:
        proc = subprocess.Popen(
            argv,
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )
    except FileNotFoundError:
        raise
    return LaunchResult(
        pid=proc.pid,
        message="Process launched in a new session (detached via KillMode=process).",
        detached=False,
    )


def _unit_main_pid(unit: str) -> int | None:
    name = unit if unit.endswith((".service", ".scope")) else f"{unit}.service"
    try:
        proc = subprocess.run(
            ["systemctl", "--user", "show", name, "-p", "MainPID", "--value"],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
    except Exception:
        return None
    raw = (proc.stdout or "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return None
