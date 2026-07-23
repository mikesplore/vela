import pytest

from app.auth import create_access_token


@pytest.mark.anyio
async def test_network_diagnostics(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    def fake_port(port: int):
        from app.domain.network import PortCheckResponse, PortProcess

        return PortCheckResponse(port=port, listening=True, processes=[PortProcess(pid=1, name="nginx")])

    def fake_health(url: str, timeout: float = 5.0):
        from app.domain.network import HealthCheckResponse

        return HealthCheckResponse(url=url, reachable=True, status_code=200, elapsed_ms=12.5)

    monkeypatch.setattr("app.services.network.check_port", fake_port)
    monkeypatch.setattr("app.services.network.health_check", fake_health)

    port_response = await async_client.get(
        "/network/port/8080",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert port_response.status_code == 200
    assert port_response.json()["listening"] is True

    health_response = await async_client.get(
        "/network/health-check",
        params={"url": "http://127.0.0.1:8765/health"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert health_response.status_code == 200
    assert health_response.json()["reachable"] is True


@pytest.mark.anyio
async def test_process_running_endpoint(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})
    monkeypatch.setattr(
        "app.routers.processes.is_process_running_svc",
        lambda name: (True, 2, [100, 200]),
    )

    response = await async_client.get(
        "/processes/running/firefox",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["running"] is True
    assert payload["count"] == 2
