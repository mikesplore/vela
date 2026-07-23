import json

import pytest

from app.services import docker as docker_service
from app.services.maintenance import (
    get_service_status,
    list_systemd_services,
    service_action,
)


def test_get_service_status_parses_show_output(monkeypatch):
    def fake_run(cmd, timeout=10):
        if cmd[:3] == ["systemctl", "show", "nginx.service"]:
            return (
                "LoadState=loaded\nActiveState=active\nSubState=running\n"
                "Description=nginx web server\nUnitFileState=enabled",
                "",
                0,
            )
        return "", "missing", 1

    monkeypatch.setattr("app.services.maintenance.run_command", fake_run)
    status, error = get_service_status("nginx", scope="system")
    assert error is None
    assert status is not None
    assert status.name == "nginx.service"
    assert status.running is True
    assert status.enabled == "enabled"


def test_list_systemd_services_filters_by_name(monkeypatch):
    payload = json.dumps(
        [
            {
                "unit": "nginx.service",
                "load": "loaded",
                "active": "active",
                "sub": "running",
                "description": "nginx",
            },
            {
                "unit": "ssh.service",
                "load": "loaded",
                "active": "active",
                "sub": "running",
                "description": "ssh",
            },
        ]
    )

    def fake_run(cmd, timeout=10):
        if cmd[:2] == ["systemctl", "list-units"]:
            return payload, "", 0
        return "", "fail", 1

    monkeypatch.setattr("app.services.maintenance.run_command", fake_run)
    services, error = list_systemd_services(filter_text="nginx", scope="system")
    assert error is None
    assert len(services) == 1
    assert services[0].name == "nginx.service"


def test_service_action_start_is_idempotent_when_running(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd, timeout=10):
        calls.append(cmd)
        if cmd[:3] == ["systemctl", "show", "nginx.service"]:
            return "LoadState=loaded\nActiveState=active\nSubState=running\nDescription=nginx\nUnitFileState=enabled", "", 0
        return "", "", 0

    monkeypatch.setattr("app.services.maintenance.run_command", fake_run)
    response, error = service_action("nginx.service", "start", scope="system")
    assert error is None
    assert response.success is True
    assert "already running" in response.message
    assert not any(cmd[:2] == ["systemctl", "start"] for cmd in calls)


def test_list_containers_parses_json_lines(monkeypatch):
    monkeypatch.setattr(docker_service, "docker_installed", lambda: True)

    def fake_run(cmd, timeout=10):
        if cmd[:2] == ["docker", "ps"]:
            return (
                '{"ID":"abc123","Names":"/web","Image":"nginx:latest","Status":"Up 2 hours","State":"running","Ports":"0.0.0.0:8080->80/tcp"}',
                "",
                0,
            )
        return "", "fail", 1

    monkeypatch.setattr(docker_service, "run_command", fake_run)
    response, error = docker_service.list_containers(all_containers=True)
    assert error is None
    assert len(response.containers) == 1
    assert response.containers[0].name == "web"
    assert response.containers[0].state == "running"
