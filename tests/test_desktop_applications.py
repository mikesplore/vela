from pathlib import Path

import pytest

from app.services import processes as processes_service


@pytest.fixture
def desktop_dir(tmp_path, monkeypatch):
    apps_dir = tmp_path / "applications"
    apps_dir.mkdir()
    (apps_dir / "google-chrome.desktop").write_text(
        """
[Desktop Entry]
Type=Application
Name=Google Chrome
GenericName=Web Browser
Exec=/usr/bin/google-chrome-stable %U
Keywords=chrome;browser;web;
Categories=Network;WebBrowser;
""".strip(),
        encoding="utf-8",
    )
    (apps_dir / "firefox.desktop").write_text(
        """
[Desktop Entry]
Type=Application
Name=Firefox
GenericName=Web Browser
Exec=firefox %u
Categories=Network;WebBrowser;
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(processes_service, "DESKTOP_DIRS", (apps_dir,))
    monkeypatch.setattr(processes_service, "_desktop_search_dirs", lambda: [apps_dir])
    monkeypatch.setattr(processes_service, "_cache_loaded_at", None)
    monkeypatch.setattr(processes_service, "_cache_entries", None)
    return apps_dir


def test_list_installed_applications(desktop_dir):
    apps = processes_service.list_installed_applications()
    assert len(apps.applications) == 2
    names = {app.name for app in apps.applications}
    assert "Google Chrome" in names
    assert "Firefox" in names


def test_list_installed_applications_filter(desktop_dir):
    apps = processes_service.list_installed_applications(filter_text="chrome")
    assert len(apps.applications) == 1
    assert apps.applications[0].name == "Google Chrome"
    assert apps.applications[0].exec_binary == "/usr/bin/google-chrome-stable"


def test_resolve_application_by_alias(desktop_dir):
    entry = processes_service.resolve_application("chrome")
    assert entry.id == "google-chrome.desktop"
    assert entry.name == "Google Chrome"


def test_resolve_application_by_display_name(desktop_dir):
    entry = processes_service.resolve_application("Firefox")
    assert entry.id == "firefox.desktop"


def test_open_installed_application_uses_exec(monkeypatch, desktop_dir):
    captured: list[list[str]] = []

    def fake_spawn(argv):
        captured.append(argv)
        return processes_service.LaunchResult(pid=123, message="ok", detached=True)

    monkeypatch.setattr(processes_service, "spawn_detached", fake_spawn)
    monkeypatch.setattr(processes_service.shutil, "which", lambda name: None)

    result = processes_service.open_installed_application("chrome")
    assert result.application_id == "google-chrome.desktop"
    assert captured[0][0] == "/usr/bin/google-chrome-stable"


def test_open_installed_application_uses_gtk_launch_when_available(monkeypatch, desktop_dir):
    captured: list[list[str]] = []

    def fake_spawn(argv):
        captured.append(argv)
        return processes_service.LaunchResult(pid=123, message="ok", detached=True)

    monkeypatch.setattr(processes_service, "spawn_detached", fake_spawn)
    monkeypatch.setattr(processes_service.shutil, "which", lambda name: "/usr/bin/gtk-launch" if name == "gtk-launch" else None)

    processes_service.open_installed_application("firefox")
    assert captured[0] == ["/usr/bin/gtk-launch", "firefox.desktop"]


def test_close_installed_application_matches_chrome_alias(monkeypatch, desktop_dir):
    class FakeProc:
        def __init__(self, pid: int, name: str, cmdline: list[str]):
            self.pid = pid
            self.info = {"pid": pid, "name": name, "cmdline": cmdline}
            self.terminated = False

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=3):
            return 0

        def kill(self):
            self.terminated = True

    processes = [
        FakeProc(100, "chrome", ["/opt/google/chrome/chrome", "--profile-directory=Default"]),
        FakeProc(200, "firefox", ["firefox"]),
    ]

    monkeypatch.setattr(processes_service.psutil, "process_iter", lambda attrs: processes)

    killed_count, app_id, app_name = processes_service.close_installed_application("chrome")
    assert killed_count == 1
    assert app_id == "google-chrome.desktop"
    assert app_name == "Google Chrome"
    assert processes[0].terminated is True
    assert processes[1].terminated is False


def test_is_process_running_uses_desktop_resolution(monkeypatch, desktop_dir):
    class FakeProc:
        def __init__(self, pid: int, name: str, cmdline: list[str]):
            self.pid = pid
            self.info = {"pid": pid, "name": name, "cmdline": cmdline}

    monkeypatch.setattr(
        processes_service.psutil,
        "process_iter",
        lambda attrs: [FakeProc(100, "chrome", ["/opt/google/chrome/chrome"])],
    )

    running, count, pids = processes_service.is_process_running("Google Chrome")
    assert running is True
    assert count == 1
    assert pids == [100]


def test_resolve_application_not_found(desktop_dir):
    with pytest.raises(processes_service.ApplicationNotFoundError) as exc:
        processes_service.resolve_application("nonexistent-app")
    assert "nonexistent-app" in str(exc.value)
