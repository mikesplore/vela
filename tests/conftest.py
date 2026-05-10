import pytest
from httpx import AsyncClient

from main import app


@pytest.fixture
async def async_client():
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        yield client
