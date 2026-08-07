import httpx
import pytest

from app.auth import create_access_token
from app.services import capabilities as capabilities_service
from app.services.gatekeeper.client import reset_token_cache
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


@pytest.mark.anyio
async def test_gatekeeper_proxy_requires_auth(async_client, monkeypatch):
    _patch_gatekeeper_config(monkeypatch, base_url="http://gatekeeper.test", token="static-token")
    resp = await async_client.get("/api/admin/audit")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_gatekeeper_proxy_forwards_get(async_client, monkeypatch):
    _patch_gatekeeper_config(monkeypatch, base_url="http://gatekeeper.test", token="static-token")

    vela_token = create_access_token({"sub": "admin"})
    captured: dict = {}

    async def handler(req: httpx.Request) -> httpx.Response:
        captured["auth"] = req.headers.get("Authorization")
        captured["path"] = req.url.path
        captured["query"] = str(req.url.query)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient

    class PatchedClient(original_client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", PatchedClient)

    resp = await async_client.get(
        "/api/admin/audit?limit=12",
        headers={"Authorization": f"Bearer {vela_token}"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert captured["auth"] == "Bearer static-token"
    assert captured["path"] == "/api/admin/audit"
    assert "limit=12" in captured["query"]


@pytest.mark.anyio
async def test_gatekeeper_proxy_forwards_post_body(async_client, monkeypatch):
    _patch_gatekeeper_config(monkeypatch, base_url="http://gatekeeper.test", token="static-token")

    vela_token = create_access_token({"sub": "admin"})
    captured: dict = {}

    async def handler(req: httpx.Request) -> httpx.Response:
        captured["method"] = req.method
        captured["path"] = req.url.path
        captured["auth"] = req.headers.get("Authorization")
        captured["json"] = req.json()
        return httpx.Response(200, json={"created": True})

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient

    class PatchedClient(original_client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", PatchedClient)

    resp = await async_client.post(
        "/api/admin/projects",
        headers={"Authorization": f"Bearer {vela_token}"},
        json={"slug": "acme"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"created": True}
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/admin/projects"
    assert captured["auth"] == "Bearer static-token"
    assert captured["json"] == {"slug": "acme"}

