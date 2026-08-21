"""Explicit, non-GUI Linux clipboard backends."""

from __future__ import annotations

import os
import shutil
import subprocess

from fastapi import HTTPException

from app.utils.desktop_env import ensure_desktop_env

COMMAND_TIMEOUT_SECONDS = 10


def _backend() -> str:
    """Choose a CLI backend from the current, refreshed desktop environment."""
    ensure_desktop_env()

    # Prefer the direct X11 selection commands.  This matches the native
    # clipboard protocol and does not start or focus any desktop application.
    if os.environ.get("DISPLAY", "").strip() and shutil.which("xclip"):
        return "xclip"
    if os.environ.get("DISPLAY", "").strip() and shutil.which("xsel"):
        return "xsel"
    if (
        os.environ.get("WAYLAND_DISPLAY", "").strip()
        and os.environ.get("XDG_RUNTIME_DIR", "").strip()
        and shutil.which("wl-copy")
        and shutil.which("wl-paste")
    ):
        return "wayland"

    raise HTTPException(
        status_code=500,
        detail=(
            "No supported command-line clipboard backend is available. "
            "Install wl-clipboard for Wayland or xclip/xsel for X11."
        ),
    )


def _run(command: list[str], *, input_text: str | None = None) -> str:
    try:
        result = subprocess.run(
            command,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError) as exc:
        raise HTTPException(status_code=500, detail=f"Clipboard command failed: {exc}") from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "clipboard command failed").strip()
        raise HTTPException(status_code=500, detail=detail)
    return result.stdout


def read_clipboard() -> str:
    backend = _backend()
    if backend == "wayland":
        return _run(["wl-paste", "--no-newline", "--type", "text"])
    if backend == "xclip":
        return _run(["xclip", "-selection", "clipboard", "-o"])
    return _run(["xsel", "--clipboard", "--output"])


def write_clipboard(text: str) -> None:
    backend = _backend()
    if backend == "wayland":
        command = ["wl-copy", "--clear"] if text == "" else ["wl-copy"]
        _run(command, input_text=None if text == "" else text)
        return
    if backend == "xclip":
        _run(["xclip", "-selection", "clipboard"], input_text=text)
        return
    _run(["xsel", "--clipboard", "--input"], input_text=text)
