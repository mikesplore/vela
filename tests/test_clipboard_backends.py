import subprocess

from app.services import clipboard


def test_wayland_backend_uses_cli_without_gui_fallback(monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setattr(clipboard, "ensure_desktop_env", lambda: None)
    monkeypatch.setattr(
        clipboard.shutil,
        "which",
        lambda command: f"/usr/bin/{command}" if command in {"wl-copy", "wl-paste"} else None,
    )

    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="clipboard text", stderr="")

    monkeypatch.setattr(clipboard.subprocess, "run", fake_run)

    clipboard.write_clipboard("hello")
    assert clipboard.read_clipboard() == "clipboard text"
    assert calls[0][0] == ["wl-copy"]
    assert calls[0][1]["input"] == "hello"
    assert calls[1][0] == ["wl-paste", "--no-newline", "--type", "text"]


def test_x11_backend_uses_xclip(monkeypatch):
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(clipboard, "ensure_desktop_env", lambda: None)
    monkeypatch.setattr(
        clipboard.shutil,
        "which",
        lambda command: "/usr/bin/xclip" if command == "xclip" else None,
    )

    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(clipboard.subprocess, "run", fake_run)
    clipboard.write_clipboard("")

    assert calls[0][0] == ["xclip", "-selection", "clipboard"]
    assert calls[0][1]["input"] == ""


def test_xclip_round_trip_uses_clipboard_selection(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(clipboard, "ensure_desktop_env", lambda: None)
    monkeypatch.setattr(
        clipboard.shutil,
        "which",
        lambda command: "/usr/bin/xclip" if command == "xclip" else None,
    )

    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        output = "Hello World\n" if command[-1] == "-o" else ""
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")

    monkeypatch.setattr(clipboard.subprocess, "run", fake_run)
    clipboard.write_clipboard("Hello World")
    assert clipboard.read_clipboard() == "Hello World\n"
    assert calls[0][0] == ["xclip", "-selection", "clipboard"]
    assert calls[0][1]["input"] == "Hello World"
    assert calls[1][0] == ["xclip", "-selection", "clipboard", "-o"]


def test_clipboard_never_uses_gui_fallback(monkeypatch):
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setattr(clipboard, "ensure_desktop_env", lambda: None)
    monkeypatch.setattr(clipboard.shutil, "which", lambda _command: None)

    try:
        clipboard.read_clipboard()
    except Exception as exc:
        assert "command-line clipboard backend" in str(exc)
    else:
        raise AssertionError("clipboard should fail without a CLI backend")
