import pytest
import httpx

from app.services import capabilities as capabilities_service
from app.services.assistant.tools import TOOL_DEFINITIONS
from app.services.gatekeeper.client import is_configured, request, reset_token_cache
from app.utils.config import get_config


@pytest.fixture(autouse=True)
def reset_gatekeeper_cache():
    reset_token_cache()
    capabilities_service._cached_response = None
    yield
    reset_token_cache()
    capabilities_service._cached_response = None


def _patch_gatekeeper_config(
    monkeypatch,
    *,
    base_url: str = "",
    token: str | None = None,
    email: str = "",
    password: str = "",
) -> None:
    cfg = get_config()
    monkeypatch.setattr(cfg, "gatekeeper_base_url", base_url)
    monkeypatch.setattr(cfg, "gatekeeper_token", token)
    monkeypatch.setattr(cfg, "gatekeeper_email", email)
    monkeypatch.setattr(cfg, "gatekeeper_password", password)


def test_gatekeeper_tools_registered():
    assert "gatekeeper_list_overdue" in TOOL_DEFINITIONS
    assert TOOL_DEFINITIONS["gatekeeper_list_overdue"]["service"] == "gatekeeper"


def test_gatekeeper_not_configured(monkeypatch):
    _patch_gatekeeper_config(monkeypatch)
    assert is_configured() is False

    snapshot = capabilities_service.refresh_capabilities()
    assert snapshot.modules["gatekeeper"].available is False
    assert "gatekeeper_list_overdue" in snapshot.assistant_tools.unavailable


def test_gatekeeper_configured_with_token(monkeypatch):
    _patch_gatekeeper_config(monkeypatch, base_url="http://127.0.0.1:8080", token="test-jwt")
    assert is_configured() is True

    snapshot = capabilities_service.refresh_capabilities()
    assert snapshot.modules["gatekeeper"].available is True
    assert "gatekeeper_list_overdue" in snapshot.assistant_tools.available


@pytest.mark.anyio
async def test_gatekeeper_request_uses_token(monkeypatch):
    _patch_gatekeeper_config(monkeypatch, base_url="http://gatekeeper.test", token="static-token")

    captured: dict = {}

    async def handler(req: httpx.Request) -> httpx.Response:
        captured["auth"] = req.headers.get("Authorization")
        captured["path"] = req.url.path
        return httpx.Response(200, json=[{"slug": "acme"}])

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient

    class PatchedClient(original_client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", PatchedClient)

    data = await request("GET", "/api/admin/projects/overdue")
    assert data == [{"slug": "acme"}]
    assert captured["auth"] == "Bearer static-token"
    assert captured["path"] == "/api/admin/projects/overdue"
