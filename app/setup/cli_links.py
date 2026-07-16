"""Install user-facing CLI entrypoints outside the virtualenv."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


CLI_NAMES = ("vela", "vela-agent")


def _path_dirs() -> list[str]:
    return [p for p in os.environ.get("PATH", "").split(":") if p]


def local_bin_on_path(local_bin: Path | None = None) -> bool:
    local_bin = local_bin or (Path.home() / ".local" / "bin")
    return str(local_bin) in _path_dirs()


def install_user_cli_links(target_dir: Path) -> list[Path]:
    """Symlink vela / vela-agent into ~/.local/bin for shell use outside the venv."""
    local_bin = Path.home() / ".local" / "bin"
    local_bin.mkdir(parents=True, exist_ok=True)

    venv_bin = target_dir / ".venv" / "bin"
    installed: list[Path] = []

    for name in CLI_NAMES:
        src = venv_bin / name
        if not src.exists():
            resolved = shutil.which(name)
            if not resolved:
                print(f"Skipping CLI link for '{name}': executable not found.")
                continue
            src = Path(resolved)

        dest = local_bin / name
        try:
            if dest.is_symlink() or dest.exists():
                dest.unlink()
            dest.symlink_to(src.resolve())
            os.chmod(dest, 0o755)
            installed.append(dest)
            print(f"Installed CLI link: {dest} -> {src.resolve()}")
        except Exception as exc:
            print(f"Could not install CLI link for '{name}': {exc}")

    if installed and not local_bin_on_path(local_bin):
        print(
            f"Note: {local_bin} is not on PATH. Add it to your shell profile so "
            "`vela` works outside the virtualenv."
        )

    return installed
