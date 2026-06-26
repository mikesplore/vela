import pytest


@pytest.mark.anyio
async def test_ping_no_auth(async_client):
    response = await async_client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"pong": True}
