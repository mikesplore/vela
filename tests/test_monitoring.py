import pytest
from app.auth import create_access_token
from app.routers import monitoring as monitoring_module
from starlette.testclient import TestClient


@pytest.mark.anyio
async def test_monitoring_cpu_endpoint_returns_usage(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})
    monkeypatch.setattr(monitoring_module, "_get_cpu_usage", lambda: monitoring_module.CPUUsage(overall=12.5, per_core=[10.0, 15.0]))

    response = await async_client.get(
        "/monitor/cpu",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["overall"] == 12.5
    assert payload["per_core"] == [10.0, 15.0]


def test_monitoring_stream_websocket_requires_auth_and_streams(monkeypatch):
    monkeypatch.setattr(monitoring_module, "get_snapshot", lambda: {"cpu": {"overall": 5.0, "per_core": [5.0]}})
    token = create_access_token({"sub": "admin"})

    with TestClient(app) as client:
        with client.websocket_connect(f"/monitor/stream?interval=1", headers={"Authorization": f"Bearer {token}"}) as websocket:
            message = websocket.receive_json()
            assert message["cpu"]["overall"] == 5.0
