from app.services.assistant.stream import _friendly_tool_name, _sse_tool


def test_friendly_tool_name_appends_confirmed_for_gated_tools():
    assert _friendly_tool_name("open_application", gate_confirmed=True) == "Opening application · Confirmed"
    assert _friendly_tool_name("close_application", gate_confirmed=True) == "Closing application · Confirmed"
    assert _friendly_tool_name("kill_process", gate_confirmed=True, pin_confirmed=True) == "Killing process · PIN confirmed"


def test_friendly_tool_name_skips_suffix_for_read_only_tools():
    assert _friendly_tool_name("get_volume", gate_confirmed=True) == "Reading audio volume"
    assert _friendly_tool_name("open_application") == "Opening application"


def test_sse_tool_includes_gate_confirmation_in_name():
    event = _sse_tool("close_application", "running", gate_confirmed=True, pin_confirmed=True)
    assert "Closing application" in event
    assert "PIN confirmed" in event
    assert '"status": "running"' in event
