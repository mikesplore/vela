import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest
from app.auth import create_access_token
from app.routers import processes as processes_module
from app.services import processes as processes_service


class FakeProcess:
    def __init__(self, pid, name, cpu_percent=0.0, memory_percent=0.0, status="running", cmdline=None):
        self.pid = pid
        self.info = {
            "name": name,
            "cpu_percent": cpu_percent,
            "memory_percent": memory_percent,
            "cmdline": cmdline or [],
            "status": status,
        }
        self.terminated = False

    def oneshot(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=0):
        return


class FakePopen:
    def __init__(self, pid=123):
        self.pid = pid


@pytest.mark.anyio
async def test_list_processes_returns_sorted_processes(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    monkeypatch.setattr(
        processes_module.psutil,
        "process_iter",
        lambda attrs: [
            FakeProcess(pid=1, name="ssh", cpu_percent=1.0, memory_percent=0.5, cmdline=["ssh"]),
            FakeProcess(pid=2, name="bash", cpu_percent=3.0, memory_percent=1.5, cmdline=["bash"]),
        ],
    )

    response = await async_client.get(
        "/processes",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["processes"]) == 2
    assert payload["processes"][0]["name"] == "bash"
    assert payload["processes"][1]["name"] == "ssh"


@pytest.mark.anyio
async def test_kill_process_by_pid(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    class FakeProc(FakeProcess):
        def __init__(self, pid):
            super().__init__(pid, "test")

    monkeypatch.setattr(processes_module.psutil, "Process", lambda pid: FakeProc(pid))

    response = await async_client.delete(
        "/processes/42",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.anyio
async def testkill_processes_by_name(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})
    killed = []

    class FakeProc(FakeProcess):
        def __init__(self, pid, name):
            super().__init__(pid, name)

    def fake_iter(attrs):
        return [FakeProc(10, "bash"), FakeProc(11, "bash"), FakeProc(12, "ssh")]

    monkeypatch.setattr(processes_module.psutil, "process_iter", fake_iter)

    response = await async_client.delete(
        "/processes/name/bash",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["killed_count"] == 2


@pytest.mark.anyio
async def test_launch_process(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})
    monkeypatch.setattr(subprocess, "Popen", lambda args: FakePopen(pid=999))

    response = await async_client.post(
        "/processes/launch",
        json={"command": "echo", "args": ["hello"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["pid"] == 999


@pytest.mark.anyio
async def test_open_application(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})
    monkeypatch.setattr(
        processes_module,
        "open_installed_application",
        lambda name, args=None: processes_service.LaunchResult(
            pid=555,
            message="Opened spotify.",
            detached=True,
            application_name="Spotify",
        ),
    )

    response = await async_client.post(
        "/processes/app/open",
        json={"name": "spotify", "args": ["--no-zygote"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["pid"] == 555


@pytest.mark.anyio
async def test_close_application(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    class FakeProc(FakeProcess):
        def __init__(self, pid, name):
            super().__init__(pid, name)

    def fake_iter(attrs):
        return [FakeProc(20, "spotify"), FakeProc(21, "Spotify"), FakeProc(22, "chrome")]

    monkeypatch.setattr(processes_module.psutil, "process_iter", fake_iter)

    response = await async_client.post(
        "/processes/app/close",
        json={"name": "spotify"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["killed_count"] == 2


@pytest.mark.anyio
async def test_window_actions_use_xdotool(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    def fakerun_command(cmd, timeout=10):
        if cmd == ["xdotool", "getwindowfocus"]:
            return "1234", "", 0
        if cmd == ["xdotool", "getwindowname", "1234"]:
            return "Test Window", "", 0
        return "", "", 0

    monkeypatch.setattr(processes_module, "run_command", fakerun_command)
    monkeypatch.setattr(processes_module, "_get_window_app_path", lambda: "/usr/bin/testapp")

    active_response = await async_client.get(
        "/processes/active-window",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert active_response.status_code == 200
    active_payload = active_response.json()
    assert active_payload["window_id"] == "1234"
    assert active_payload["title"] == "Test Window"
    assert active_payload["app_name"] == "/usr/bin/testapp"

    minimize_response = await async_client.post(
        "/processes/window/minimize",
        json={"window_id": "1234"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert minimize_response.status_code == 200
    assert minimize_response.json()["success"] is True

    close_response = await async_client.post(
        "/processes/window/close",
        json={"window_id": "1234"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert close_response.status_code == 200
    assert close_response.json()["success"] is True
