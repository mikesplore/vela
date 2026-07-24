import pytest
from app.auth import create_access_token

from app.services import capabilities as capabilities_service
from app.services.assistant.tools import TOOL_DEFINITIONS, build_system_tool_prompt


@pytest.fixture
def auth_headers():
    token = create_access_token({"sub": "admin"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def reset_capabilities_cache():
    capabilities_service._cached_response = None
    yield
    capabilities_service._cached_response = None


@pytest.mark.anyio
async def test_capabilities_endpoint_requires_auth(async_client):
    response = await async_client.get("/capabilities")
    assert response.status_code == 401


@pytest.mark.anyio
async def test_capabilities_endpoint_returns_snapshot(async_client, auth_headers):
    response = await async_client.get("/capabilities", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert "modules" in payload
    assert "assistant_tools" in payload
    assert "monitoring" in payload["modules"]
    assert isinstance(payload["assistant_tools"]["available"], list)
    assert len(payload["assistant_tools"]["available"]) > 0


@pytest.mark.anyio
async def test_capabilities_refresh_endpoint(async_client, auth_headers):
    response = await async_client.post("/capabilities/refresh", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["tools_available"] > 0
    assert payload["modules_available"] > 0
    assert payload["checked_at"]


@pytest.mark.anyio
async def test_root_includes_available_modules(async_client):
    response = await async_client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert "enabled_modules" in payload
    assert "available_modules" in payload
    assert isinstance(payload["available_modules"], list)


def test_headless_marks_desktop_tools_unavailable(monkeypatch):
    monkeypatch.setattr(capabilities_service, "_has_desktop_session", lambda: False)

    snapshot = capabilities_service.refresh_capabilities()
    assert snapshot.modules["display"].available is False
    assert "display_screenshot" in snapshot.assistant_tools.unavailable


def test_docker_unavailable_when_cli_missing(monkeypatch):
    monkeypatch.setattr(capabilities_service.shutil, "which", lambda cmd: None if cmd == "docker" else "/usr/bin/true")

    snapshot = capabilities_service.refresh_capabilities()
    assert snapshot.modules["docker"].available is False
    assert snapshot.modules["docker"].reason == "Docker CLI not installed"
    assert "list_docker_containers" in snapshot.assistant_tools.unavailable


def test_clipboard_module_available_when_backend_present(monkeypatch):
    monkeypatch.setattr(
        capabilities_service.shutil,
        "which",
        lambda cmd: "/usr/bin/xclip" if cmd == "xclip" else None,
    )

    snapshot = capabilities_service.refresh_capabilities()

    assert "clipboard" in snapshot.modules
    assert snapshot.modules["clipboard"].available is True
    assert snapshot.modules["clipboard"].metadata["backends"] == ["xclip"]
    assert "read_clipboard" in snapshot.assistant_tools.available


def test_clipboard_unavailable_when_no_backend(monkeypatch):
    monkeypatch.setattr(capabilities_service.shutil, "which", lambda _cmd: None)

    snapshot = capabilities_service.refresh_capabilities()

    assert snapshot.modules["clipboard"].available is False
    assert "clipboard backend" in (snapshot.modules["clipboard"].reason or "").lower()
    assert "read_clipboard" in snapshot.assistant_tools.unavailable


def test_assistant_prompt_excludes_unavailable_tools(monkeypatch):
    monkeypatch.setattr(capabilities_service, "_has_desktop_session", lambda: False)
    capabilities_service.refresh_capabilities()

    available = capabilities_service.get_available_tool_names()
    prompt = build_system_tool_prompt(available)

    assert "- display_screenshot:" not in prompt
    assert "get_snapshot" in prompt
    assert len(available) < len(TOOL_DEFINITIONS)
