"""Resolve which .env file Vela services actually load."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

SYSTEMD_USER_DIR = Path.home() / ".config/systemd/user"


def _parse_systemd_value(unit_text: str, key: str) -> str | None:
    prefix = f"{key}="
    for line in unit_text.splitlines():
        line = line.strip()
        if line.startswith(prefix):
            return line.split("=", 1)[1].strip()
    return None


def resolve_active_dotenv_path() -> Path:
    """Return the credentials .env used by vela-agent (or the expected path)."""
    agent_unit = SYSTEMD_USER_DIR / "vela-agent.service"
    if agent_unit.is_file():
        env_file = _parse_systemd_value(agent_unit.read_text(encoding="utf-8"), "EnvironmentFile")
        if env_file:
            return Path(env_file).expanduser().resolve()

    vela_unit = SYSTEMD_USER_DIR / "vela.service"
    if vela_unit.is_file():
        working_dir = _parse_systemd_value(vela_unit.read_text(encoding="utf-8"), "WorkingDirectory")
        if working_dir:
            return (Path(working_dir).expanduser() / ".env").resolve()

    from app.utils.config import ENV_CANDIDATES

    for candidate in ENV_CANDIDATES:
        if candidate.exists():
            return candidate.resolve()
    return (Path.cwd() / ".env").resolve()


def open_dotenv_in_editor(path: Path | None = None) -> Path:
    """Open the active Vela .env in the user's editor. Returns the path used."""
    env_path = (path or resolve_active_dotenv_path()).expanduser()
    env_path.parent.mkdir(parents=True, exist_ok=True)
    if not env_path.exists():
        env_path.touch(mode=0o600)
    else:
        os.chmod(env_path, 0o600)

    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if editor:
        subprocess.run([*shlex.split(editor), str(env_path)], check=False)
    else:
        for candidate in ("cursor", "code", "nano", "vi", "gedit", "xdg-open"):
            if shutil.which(candidate):
                subprocess.run([candidate, str(env_path)], check=False)
                break
        else:
            print(f"Active Vela .env: {env_path}")
            print("Set EDITOR to open it automatically.")

    return env_path
