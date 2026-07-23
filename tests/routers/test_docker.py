import pytest

from app.auth import create_access_token
from app.routers import docker as docker_router
from app.routers import maintenance as maintenance_module


@pytest.mark.anyio
async def test_service_status_and_idempotent_start(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})
    calls: list[list[str]] = []

    def fakerun_command(cmd, timeout=10):
        calls.append(cmd)
        if cmd[:3] == ["systemctl", "show", "nginx.service"]:
            return (
                "LoadState=loaded\nActiveState=active\nSubState=running\n"
                "Description=nginx\nUnitFileState=enabled",
                "",
                0,
            )
        if cmd[:2] == ["systemctl", "start"]:
            return "", "", 0
        return "", "", 1

    monkeypatch.setattr(maintenance_module, "run_command", fakerun_command)
    monkeypatch.setattr("app.services.maintenance.run_command", fakerun_command)

    status_response = await async_client.get(
        "/maintenance/service/status",
        params={"name": "nginx.service"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert status_response.status_code == 200
    assert status_response.json()["running"] is True

    start_response = await async_client.post(
        "/maintenance/service/start",
        params={"name": "nginx.service"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert start_response.status_code == 200
    assert "already running" in start_response.json()["message"]
    assert not any(cmd[:2] == ["systemctl", "start"] for cmd in calls)


@pytest.mark.anyio
async def test_docker_info_and_containers(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    def fake_info():
        from app.domain.docker import DockerInfoResponse

        return DockerInfoResponse(installed=True, running=True, version="27.0.0", containers_running=1)

    def fake_list(all_containers=True, filter_text=None):
        from app.domain.docker import DockerContainer, DockerContainerListResponse

        return DockerContainerListResponse(
            containers=[DockerContainer(id="abc", name="web", image="nginx", status="Up", state="running")]
        ), None

    monkeypatch.setattr(docker_router.docker_service, "get_docker_info", fake_info)
    monkeypatch.setattr(docker_router.docker_service, "list_containers", fake_list)

    info_response = await async_client.get("/docker/info", headers={"Authorization": f"Bearer {token}"})
    assert info_response.status_code == 200
    assert info_response.json()["running"] is True

    containers_response = await async_client.get("/docker/containers", headers={"Authorization": f"Bearer {token}"})
    assert containers_response.status_code == 200
    assert containers_response.json()["containers"][0]["name"] == "web"
