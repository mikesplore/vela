import pytest

from auth import create_access_token
from routers import power as power_module


@pytest.mark.anyio
async def test_power_shutdown(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    def fake_run_command(cmd, timeout=10):
        return "", "", 0

    monkeypatch.setattr(power_module, "_run_command", fake_run_command)

    response = await async_client.post(
        "/power/shutdown",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["message"] == "shutdown initiated"
