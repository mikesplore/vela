"""Install user-facing CLI entrypoints outside the virtualenv."""

from __future__ import annotations

import os
from pathlib import Path


CLI_NAMES = ("vela", "vela-agent")


def _path_dirs() -> list[str]:
    return [p for p in os.environ.get("PATH", "").split(":") if p]


def local_bin_on_path(local_bin: Path | None = None) -> bool:
    local_bin = local_bin or (Path.home() / ".local" / "bin")
    return str(local_bin) in _path_dirs()


def _is_usable_cli_source(src: Path, local_bin: Path) -> bool:
    """Accept only real venv executables — never anything under ~/.local/bin."""
    if not src.exists():
        return False
    try:
        resolved = src.resolve()
    except Exception:
        return False
    # Reject loops: source must not be (or live under) the destination directory.
    try:
        resolved.relative_to(local_bin.resolve())
        return False
    except ValueError:
        pass
    return resolved.is_file()


def install_user_cli_links(target_dir: Path) -> list[Path]:
    """Symlink vela / vela-agent into ~/.local/bin for shell use outside the venv.

    Always points at ``<target_dir>/.venv/bin/<cmd>``. Never uses ``which``,
    which can resolve to ~/.local/bin and create self-referential loops.
    """
    local_bin = Path.home() / ".local" / "bin"
    local_bin.mkdir(parents=True, exist_ok=True)

    venv_bin = (target_dir / ".venv" / "bin").resolve()
    installed: list[Path] = []

    for name in CLI_NAMES:
        src = venv_bin / name
        dest = local_bin / name

        if not _is_usable_cli_source(src, local_bin):
            print(f"Skipping CLI link for '{name}': expected executable at {src}")
            continue

        src_resolved = src.resolve()
        try:
            if dest.is_symlink() or dest.exists():
                dest.unlink()
            dest.symlink_to(src_resolved)
            installed.append(dest)
            print(f"Installed CLI link: {dest} -> {src_resolved}")
        except Exception as exc:
            print(f"Could not install CLI link for '{name}': {exc}")

    if installed and not local_bin_on_path(local_bin):
        print(
            f"Note: {local_bin} is not on PATH. Add it to your shell profile so "
            "`vela` works outside the virtualenv."
        )

    return installed
