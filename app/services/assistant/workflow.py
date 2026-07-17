"""Dependency-aware preparation for assistant tool plans."""
from __future__ import annotations

import re
from typing import Any


_CONDITIONAL_REQUEST = re.compile(r"\bif\b|\botherwise\b|\bdepending\s+on\b", re.IGNORECASE)


def needs_conditional_followup(user_message: str, tool_calls: list[dict[str, Any]]) -> bool:
    """True only for an observation-only first stage of an if/otherwise request."""
    real_calls = [call for call in tool_calls if call.get("tool") and call.get("tool") != "none"]
    return bool(
        real_calls
        and _CONDITIONAL_REQUEST.search(user_message)
        and all(_is_observation_tool(str(call["tool"])) for call in real_calls)
    )


def _is_observation_tool(tool_name: str) -> bool:
    return (
        tool_name.startswith("get_")
        or tool_name.startswith("list_")
        or tool_name in {"search_files", "active_window"}
    )


def prepare_tool_calls(tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize planner calls and add safe, deterministic Spotify dependencies.

    ``depends_on`` values from the planner refer to positions in its original
    JSON array. Internally, opaque IDs are used so injected calls are safe.
    """
    prepared: list[dict[str, Any]] = []
    source_index_to_id: dict[int, str] = {}

    for source_index, raw in enumerate(tool_calls):
        tool = raw.get("tool")
        if not tool or tool == "none":
            continue
        call_id = f"call-{source_index}"
        call = {
            "id": call_id,
            "source_index": source_index,
            "tool": str(tool),
            "tool_input": raw.get("tool_input") or {},
            "depends_on_ids": [],
        }
        prepared.append(call)
        source_index_to_id[source_index] = call_id

    for call, raw in zip(prepared, (c for c in tool_calls if c.get("tool") and c["tool"] != "none")):
        raw_dependencies = raw.get("depends_on") or []
        if not isinstance(raw_dependencies, list):
            raw_dependencies = []
        for dependency in raw_dependencies:
            if isinstance(dependency, int) and dependency in source_index_to_id:
                dependency_id = source_index_to_id[dependency]
                if dependency_id != call["id"] and dependency_id not in call["depends_on_ids"]:
                    call["depends_on_ids"].append(dependency_id)

    _apply_spotify_workflow(prepared)
    return prepared


def next_execution_stage(
    prepared_calls: list[dict[str, Any]],
    completed: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[tuple[dict[str, Any], dict[str, Any]]]]:
    """Return calls that may run now, plus calls blocked by failed dependencies."""
    ready: list[dict[str, Any]] = []
    skipped: list[tuple[dict[str, Any], dict[str, Any]]] = []

    for call in prepared_calls:
        if call["id"] in completed:
            continue
        dependencies = call["depends_on_ids"]
        if any(dependency not in completed for dependency in dependencies):
            continue
        failed = [dependency for dependency in dependencies if completed[dependency].get("error")]
        if failed:
            skipped.append((
                call,
                {
                    "tool": call["tool"],
                    "result": {},
                    "error": "Skipped because prerequisite tool failed.",
                },
            ))
        else:
            ready.append(call)

    # Cycles or unsupported dependency references must not leave a request hung.
    if not ready and not skipped:
        pending = [call for call in prepared_calls if call["id"] not in completed]
        for call in pending:
            skipped.append((
                call,
                {
                    "tool": call["tool"],
                    "result": {},
                    "error": "Skipped because tool dependencies are cyclic or unresolved.",
                },
            ))
    return ready, skipped


def _apply_spotify_workflow(calls: list[dict[str, Any]]) -> None:
    """Enforce Spotify launch → local activation → search/play order.

    Opening Spotify and starting a track cannot safely happen concurrently.
    If a plan launches Spotify and asks to play a search result, inject the
    local toggle activation step when the planner omitted it.
    """
    spotify_launch = next(
        (
            call for call in calls
            if call["tool"] == "open_application"
            and str((call["tool_input"] or {}).get("name", "")).strip().casefold() == "spotify"
        ),
        None,
    )
    search_play = next((call for call in calls if call["tool"] == "search_and_play"), None)
    if not spotify_launch or not search_play:
        return

    toggle = next((call for call in calls if call["tool"] == "toggle_play_pause"), None)
    if toggle is None:
        launch_position = calls.index(spotify_launch)
        toggle = {
            "id": "generated-spotify-toggle",
            "source_index": None,
            "tool": "toggle_play_pause",
            "tool_input": {},
            "depends_on_ids": [],
        }
        calls.insert(launch_position + 1, toggle)

    _add_dependency(toggle, spotify_launch["id"])
    _add_dependency(search_play, toggle["id"])


def _add_dependency(call: dict[str, Any], dependency_id: str) -> None:
    if call["id"] != dependency_id and dependency_id not in call["depends_on_ids"]:
        call["depends_on_ids"].append(dependency_id)
