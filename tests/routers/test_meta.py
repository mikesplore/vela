import pytest
from httpx import AsyncClient

from app.main import app

pytestmark = pytest.mark.asyncio

async def test_count_tools(authenticated_client: AsyncClient):
    response = await authenticated_client.get("/meta/tools/count")
    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert isinstance(data["count"], int)
    assert data["count"] > 0

async def test_list_tools(authenticated_client: AsyncClient):
    response = await authenticated_client.get("/meta/tools")
    assert response.status_code == 200
    data = response.json()
    assert "tools" in data
    assert isinstance(data["tools"], list)
    assert len(data["tools"]) > 0

async def test_list_tools_with_filter(authenticated_client: AsyncClient):
    response = await authenticated_client.get("/meta/tools?filter=count_tools")
    assert response.status_code == 200
    data = response.json()
    assert "tools" in data
    assert "count_tools" in data["tools"]
