import pytest

from app.auth import create_access_token
from app.routers import power as power_module


@pytest.mark.anyio
async def test_power_shutdown(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    def fakerun_command(cmd, timeout=10):
        return "", "", 0

    monkeypatch.setattr(power_module, "run_command", fakerun_command)

    response = await async_client.post(
        "/power/shutdown",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["message"] == "shutdown initiated"


@pytest.mark.anyio
async def test_powerschedule_shutdown(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    def fakerun_command(cmd, timeout=10):
        assert cmd[:2] == ["shutdown", "-h"]
        return "", "", 0

    monkeypatch.setattr(power_module, "run_command", fakerun_command)

    response = await async_client.post(
        "/power/schedule-shutdown",
        json={"at": "2099-12-31T23:00:00"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert "shutdown scheduled for" in payload["message"]


@pytest.mark.anyio
async def test_power_cancel_shutdown(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    def fakerun_command(cmd, timeout=10):
        assert cmd == ["shutdown", "-c"]
        return "", "", 0

    monkeypatch.setattr(power_module, "run_command", fakerun_command)

    response = await async_client.post(
        "/power/cancel-shutdown",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["message"] == "shutdown canceled"


@pytest.mark.anyio
async def test_power_profile_get(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    def fakerun_command(cmd, timeout=10):
        if cmd == ["powerprofilesctl", "get"]:
            return "balanced", "", 0
        return "", "", 0

    monkeypatch.setattr(power_module, "run_command", fakerun_command)

    response = await async_client.get(
        "/power/profile",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"] == "balanced"


@pytest.mark.anyio
async def test_power_profile_set(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    def fakerun_command(cmd, timeout=10):
        assert cmd == ["powerprofilesctl", "set", "performance"]
        return "", "", 0

    monkeypatch.setattr(power_module, "run_command", fakerun_command)

    response = await async_client.post(
        "/power/profile",
        json={"profile": "performance"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"] == "performance"
