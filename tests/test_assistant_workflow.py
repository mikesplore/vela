import asyncio

import pytest

from app.services.assistant.tool_exec import execute_tool_plan
from app.services.assistant.workflow import prepare_tool_calls


def test_spotify_workflow_injects_activation_and_dependencies():
    prepared = prepare_tool_calls([
        {"tool": "open_application", "tool_input": {"name": "spotify"}},
        {"tool": "search_and_play", "tool_input": {"query": "Wicked by Future"}},
    ])

    assert [call["tool"] for call in prepared] == [
        "open_application",
        "toggle_play_pause",
        "search_and_play",
    ]
    assert prepared[1]["depends_on_ids"] == [prepared[0]["id"]]
    assert prepared[2]["depends_on_ids"] == [prepared[1]["id"]]


@pytest.mark.anyio
async def test_dependency_plan_keeps_independent_calls_parallel():
    prepared = prepare_tool_calls([
        {"tool": "open_application", "tool_input": {"name": "spotify"}},
        {"tool": "get_battery", "tool_input": {}},
        {"tool": "search_and_play", "tool_input": {"query": "Wicked"}, "depends_on": [0]},
    ])
    started: list[str] = []
    finished: list[str] = []

    async def execute(call):
        started.append(call["tool"])
        await asyncio.sleep(0.01)
        finished.append(call["tool"])
        return {"tool": call["tool"], "result": {}, "error": None}

    results = await execute_tool_plan(prepared, execute)

    # Spotify activation is injected and search/play cannot start before it finishes.
    assert started[:2] == ["open_application", "get_battery"]
    assert started[2] == "toggle_play_pause"
    assert started[3] == "search_and_play"
    assert finished.index("open_application") < started.index("toggle_play_pause")
    assert finished.index("toggle_play_pause") < started.index("search_and_play")
    assert [result["tool"] for result in results] == [
        "open_application",
        "toggle_play_pause",
        "get_battery",
        "search_and_play",
    ]


@pytest.mark.anyio
async def test_failed_prerequisite_skips_dependent_call():
    prepared = prepare_tool_calls([
        {"tool": "open_application", "tool_input": {"name": "spotify"}},
        {"tool": "search_and_play", "tool_input": {"query": "Wicked"}},
    ])
    executed: list[str] = []

    async def execute(call):
        executed.append(call["tool"])
        if call["tool"] == "open_application":
            return {"tool": call["tool"], "result": {}, "error": "Spotify did not launch"}
        return {"tool": call["tool"], "result": {}, "error": None}

    results = await execute_tool_plan(prepared, execute)

    assert executed == ["open_application"]
    assert all(result["error"] for result in results)
    assert results[-1]["error"] == "Skipped because prerequisite tool failed."
