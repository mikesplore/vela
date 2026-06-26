from datetime import timedelta

import pytest
from auth import create_access_token
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.mark.anyio
async def test_token_issuance_valid_credentials():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/auth/token",
            json={"username": "admin", "password": "admin123"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["access_token"]
    assert payload["token_type"] == "bearer"


@pytest.mark.anyio
async def test_token_issuance_invalid_credentials():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/auth/token",
            json={"username": "admin", "password": "wrongpass"},
        )

    assert response.status_code == 401
    assert response.json()["message"] == "Invalid username or password"


@pytest.mark.anyio
async def test_protected_route_rejects_without_token():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/auth/me")

    assert response.status_code == 401
    assert response.json()["message"] in {"Not authenticated", "Could not validate credentials"}


@pytest.mark.anyio
async def test_expired_token_is_rejected():
    token = create_access_token({"sub": "admin"}, expires_delta=timedelta(seconds=-1))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"
