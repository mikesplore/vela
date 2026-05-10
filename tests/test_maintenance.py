import pytest
from auth import create_access_token
from routers import maintenance as maintenance_module


@pytest.mark.anyio
async def test_maintenance_logs_updates_services_and_sync(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    def fake_run_command(cmd, timeout=10):
        if cmd[:2] == ["journalctl", "-u"]:
            return "line1\nline2", "", 0
        if cmd[:2] == ["apt", "list"]:
            return "package1/now 1.0-1 amd64 [upgradable]", "", 0
        if cmd[:2] == ["apt-get", "update"]:
            return "Updated cache", "", 0
        if cmd[:2] == ["apt-get", "upgrade"]:
            return "Upgraded", "", 0
        if cmd[:2] == ["timedatectl", "set-ntp"]:
            return "NTP enabled", "", 0
        if cmd[:2] == ["systemctl", "list-units"]:
            return "nginx.service loaded active running nginx web server", "", 0
        if cmd[:2] == ["systemctl", "restart"]:
            return "", "", 0
        if cmd[:2] == ["systemctl", "stop"]:
            return "", "", 0
        if cmd[:2] == ["systemctl", "start"]:
            return "", "", 0
        return "", "", 1

    monkeypatch.setattr(maintenance_module, "_run_command", fake_run_command)
    monkeypatch.setattr(maintenance_module.shutil, "which", lambda name: "/usr/bin/apt" if name == "apt-get" else None)

    logs_response = await async_client.get(
        "/maintenance/logs",
        params={"service": "nginx.service", "lines": 10},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logs_response.status_code == 200
    assert logs_response.json()["lines"] == ["line1", "line2"]

    updates_response = await async_client.get(
        "/maintenance/updates",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert updates_response.status_code == 200
    assert updates_response.json()["manager"] == "apt"

    update_response = await async_client.post(
        "/maintenance/update",
        params={"confirm": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["success"] is True

    sync_response = await async_client.post(
        "/maintenance/sync-time",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert sync_response.status_code == 200
    assert sync_response.json()["message"] == "Time synchronization enabled."

    services_response = await async_client.get(
        "/maintenance/services",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert services_response.status_code == 200
    assert services_response.json()["services"][0]["name"] == "nginx.service"

    restart_response = await async_client.post(
        "/maintenance/service/restart",
        params={"name": "nginx.service"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert restart_response.status_code == 200
    assert restart_response.json()["success"] is True

    stop_response = await async_client.post(
        "/maintenance/service/stop",
        params={"name": "nginx.service"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert stop_response.status_code == 200
    assert stop_response.json()["success"] is True

    start_response = await async_client.post(
        "/maintenance/service/start",
        params={"name": "nginx.service"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert start_response.status_code == 200
    assert start_response.json()["success"] is True
