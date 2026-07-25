import importlib

import pytest

from app.routers import registry
from app.services import capabilities as capabilities_service


@pytest.fixture(autouse=True)
def reset_capabilities_cache():
    capabilities_service._cached_response = None
    yield
    capabilities_service._cached_response = None


def test_startup_enabled_modules_excludes_headless_desktop(monkeypatch):
    monkeypatch.setattr(capabilities_service, "_has_desktop_session", lambda: False)

    enabled = capabilities_service.get_startup_enabled_modules()

    assert "monitoring" in enabled
    assert "display" not in enabled
    assert "clipboard" not in enabled
    assert "input_control" not in enabled
    assert "notifications" not in enabled
    assert "media" not in enabled


def test_load_routers_skips_unavailable_modules(monkeypatch):
    monkeypatch.setattr(
        capabilities_service,
        "get_startup_enabled_modules",
        lambda: frozenset({"monitoring", "network", "processes"}),
    )

    routers = registry.load_routers(capabilities_service.get_startup_enabled_modules())
    loaded_paths = {router.prefix for router in routers}

    assert "/monitor" in loaded_paths
    assert "/network" in loaded_paths
    assert "/display" not in loaded_paths
    assert "/assistant" not in loaded_paths


def test_load_routers_does_not_import_skipped_modules(monkeypatch):
    monkeypatch.setattr(
        capabilities_service,
        "get_startup_enabled_modules",
        lambda: frozenset({"monitoring"}),
    )

    for module_name in ("app.routers.display", "app.routers.assistant", "app.routers.spotify"):
        if module_name in importlib.sys.modules:
            del importlib.sys.modules[module_name]

    registry.load_routers(frozenset({"monitoring"}))

    assert "app.routers.display" not in importlib.sys.modules
    assert "app.routers.assistant" not in importlib.sys.modules
    assert "app.routers.spotify" not in importlib.sys.modules
    assert "app.routers.monitoring" in importlib.sys.modules
