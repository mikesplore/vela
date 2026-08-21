from datetime import UTC, datetime

import pytest

from app.services import capabilities as capabilities_service
from app.services.assistant import helpers
from app.services.assistant.tools import build_system_tool_prompt, tools_for_domains
from app.services.assistant.workflow import split_unavailable_tool_calls


def _snapshot(tools: set[str]) -> capabilities_service.ToolCapabilitySnapshot:
    return capabilities_service.ToolCapabilitySnapshot(
        available_tools=frozenset(tools),
        checked_at=datetime.now(UTC),
        snapshot_id="test-snapshot",
    )


def test_audio_volume_tools_need_amixer_not_pactl(monkeypatch):
    monkeypatch.setattr(
        capabilities_service.shutil,
        "which",
        lambda command: "/usr/bin/amixer" if command == "amixer" else None,
    )
    monkeypatch.setattr(capabilities_service, "_has_desktop_session", lambda: True)

    available = capabilities_service.get_available_tool_names()

    assert "set_volume" in available
    assert "volume_up" in available
    assert "audio_devices" not in available


def test_generated_audio_domain_contains_authoritative_tool_names():
    assert tools_for_domains(["audio"]) >= {
        "get_volume", "set_volume", "volume_up", "volume_down", "mute_audio", "audio_devices",
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    "router_payload",
    [
        {"domains": ["audio"], "confidence": 0.4, "fallback": True},
        {"domains": ["old_audio_domain"], "confidence": 0.95},
    ],
)
async def test_domain_router_uncertainty_or_stale_domain_falls_open(monkeypatch, router_payload):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": __import__("json").dumps(router_payload)}}]}

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(helpers, "get_api_key", lambda: "test-key")
    monkeypatch.setattr(helpers, "AsyncClient", Client)

    assert await helpers.plan_domain_selection("set volume to 50") == []


def test_empty_domain_filter_does_not_broaden_prompt():
    prompt = build_system_tool_prompt(
        available_tools={"set_volume"},
        selected_domains=["does_not_exist"],
    )

    assert "- set_volume:" not in prompt
    assert "- get_system_cpu:" not in prompt


def test_workflow_reuses_capability_snapshot(monkeypatch):
    snapshot = _snapshot({"set_volume"})
    monkeypatch.setattr(
        capabilities_service,
        "get_available_tool_names",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("live probe repeated")),
    )

    allowed, rejected = split_unavailable_tool_calls(
        [{"tool": "set_volume", "tool_input": {"value": 50}}], snapshot
    )

    assert len(allowed) == 1
    assert rejected == []


@pytest.mark.anyio
async def test_direct_volume_request_skips_domain_router(monkeypatch):
    snapshot = _snapshot({"set_volume"})
    calls = []

    async def unexpected_router(*_args, **_kwargs):
        raise AssertionError("direct volume command should bypass domain router")

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": '[{"tool":"set_volume","tool_input":{"value":50}}]'}}]}

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **kwargs):
            calls.append(kwargs["json"]["messages"])
            return Response()

    monkeypatch.setattr(helpers, "plan_domain_selection", unexpected_router)
    monkeypatch.setattr(helpers, "get_api_key", lambda: "test-key")
    monkeypatch.setattr(helpers, "AsyncClient", Client)

    result = await helpers.plan_tool_calls(
        "set volume to 50", capability_snapshot=snapshot, request_id="req-1"
    )

    assert result[0]["tool"] == "set_volume"
    assert any("- set_volume:" in message["content"] for message in calls[0])
