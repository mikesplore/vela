from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel

from config import Config

config = Config()

RiskLevel = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class ToolPolicy:
    risk_level: RiskLevel
    requires_confirmation: bool = False
    requires_auth: bool = False


class ConfirmationCard(BaseModel):
    """Structured confirmation data for rendering a UI card."""
    title: str
    description: str
    action_type: str
    tool_count: int
    requires_auth: bool
    action_details: list[str]
    prompt_text: str
    pin_attempts_remaining: int | None = None
    pin_max_attempts: int | None = None


@dataclass
class PendingAction:
    action_id: str
    user_id: str
    session_id: str
    user_message: str
    tool_calls: list[dict[str, Any]]
    prompt: str
    requires_auth: bool
    created_at: datetime
    expires_at: datetime
    pin_attempts: int = 0


LOW_RISK_TOOLS = {
    "get_system_info",
    "get_system_cpu",
    "get_system_ram",
    "get_system_gpu",
    "get_system_disk",
    "get_system_os",
    "get_system_usb",
    "get_system_monitors",
    "get_system_bios",
    "get_network_ip",
    "get_network_location",
    "get_wifi_status",
    "list_wifi_networks",
    "list_bluetooth_devices",
    "ping_host",
    "get_snapshot",
    "monitor_cpu",
    "monitor_ram",
    "monitor_gpu",
    "monitor_disk_io",
    "monitor_network_io",
    "monitor_temperatures",
    "monitor_fans",
    "get_battery",
    "get_top_processes",
    "get_volume",
    "set_volume",
    "volume_up",
    "volume_down",
    "mute_audio",
    "audio_devices",
    "get_media_status",
    "toggle_play_pause",
    "next_track",
    "previous_track",
    "seek_media",
    "read_clipboard",
    "write_clipboard",
    "clear_clipboard",
    "display_screenshot",
    "display_record",
    "monitor_off",
    "monitor_on",
    "get_display_brightness",
    "set_display_brightness",
    "get_resolution",
    "set_resolution",
    "rotate_display",
    "lock_screen_display",
    "set_night_light",
    "list_files",
    "download_file",
    "get_disk_usage",
    "search_files",
    "list_processes",
    "list_jobs",
    "cancel_job",
    "power_sleep",
}

MEDIUM_RISK_TOOLS = {
    "connect_wifi",
    "disconnect_wifi",
    "toggle_wifi",
    "toggle_bluetooth",
    "pair_bluetooth_device",
    "unpair_bluetooth_device",
    "type_keyboard",
    "press_keyboard_keys",
    "move_mouse",
    "click_mouse",
    "double_click_mouse",
    "scroll_mouse",
    "launch_process",
    "open_application",
    "open_path",
    "rename_path",
    "schedule_job",
    "run_job_now",
    "make_directory",
    "zip_paths",
    "unzip_path",
}

HIGH_RISK_TOOLS = {
    "delete_path",
    "upload_file",
    "kill_process",
    "kill_process_by_name",
    "power_shutdown",
    "power_restart",
    "power_hibernate",
}

PENDING_ACTIONS: dict[str, PendingAction] = {}
PIN_MAX_ATTEMPTS = 3


def _pending_action_key(user_id: str, session_id: str) -> str:
    """Generate a unique key for storing pending actions per user per session/device."""
    return f"{user_id}|{session_id}"


def get_tool_policy(tool_name: str) -> ToolPolicy:
    if tool_name in HIGH_RISK_TOOLS:
        return ToolPolicy(risk_level="high", requires_confirmation=True, requires_auth=True)
    if tool_name in MEDIUM_RISK_TOOLS:
        return ToolPolicy(risk_level="medium", requires_confirmation=True, requires_auth=False)
    return ToolPolicy(risk_level="low")


def _tool_summary(tool_name: str, tool_input: dict[str, Any]) -> str:
    if tool_name in {"kill_process", "kill_process_by_name"}:
        pid = tool_input.get("pid")
        name = tool_input.get("name")
        if pid is not None:
            return f"kill process {pid}"
        if name:
            return f'kill process(es) matching "{name}"'
    if tool_name == "delete_path":
        return f'delete {tool_input.get("path", "the selected path")}'
    if tool_name == "rename_path":
        return f'rename {tool_input.get("from", "the source path")} to {tool_input.get("to", "the destination path")} '
    if tool_name == "upload_file":
        return f'upload a file to {tool_input.get("path", "the selected destination")}'
    if tool_name == "power_shutdown":
        return "shut down the machine"
    if tool_name == "power_restart":
        return "restart the machine"
    if tool_name == "power_hibernate":
        return "hibernate the machine"
    if tool_name == "connect_wifi":
        return f'connect to WiFi network {tool_input.get("ssid", "<unknown>")}'
    if tool_name == "toggle_wifi":
        return "toggle WiFi radio"
    if tool_name == "toggle_bluetooth":
        return "toggle Bluetooth radio"
    if tool_name == "pair_bluetooth_device":
        return f'pair Bluetooth device {tool_input.get("address", "<unknown>")}'
    if tool_name == "unpair_bluetooth_device":
        return f'unpair Bluetooth device {tool_input.get("address", "<unknown>")}'
    if tool_name == "type_keyboard":
        return "type into the active window"
    if tool_name == "press_keyboard_keys":
        return "press keyboard shortcuts"
    if tool_name == "move_mouse":
        return "move the mouse cursor"
    if tool_name == "click_mouse":
        return "click the mouse"
    if tool_name == "double_click_mouse":
        return "double-click the mouse"
    if tool_name == "scroll_mouse":
        return "scroll the mouse wheel"
    if tool_name == "launch_process":
        return f'launch {tool_input.get("command", "the requested process")}'
    if tool_name == "open_application":
        return f'open application {tool_input.get("name", "the requested app")}'
    if tool_name == "open_path":
        return f'open {tool_input.get("path", "the requested path")}'
    if tool_name == "schedule_job":
        return "schedule a job"
    if tool_name == "run_job_now":
        return f'run scheduled job {tool_input.get("task_id", "<unknown>")} now'
    if tool_name == "make_directory":
        return f'create directory {tool_input.get("path", "the requested path")}'
    if tool_name == "zip_paths":
        return "create a zip archive"
    if tool_name == "unzip_path":
        return f'unzip {tool_input.get("path", "the selected archive")}'
    return tool_name.replace("_", " ")


def build_confirmation_card(tool_calls: list[dict[str, Any]], requires_auth: bool, pin_attempts: int = 0) -> ConfirmationCard:
    """Build a structured confirmation card for UI rendering."""
    if not tool_calls:
        return ConfirmationCard(
            title="No Action",
            description="No pending action is available.",
            action_type="none",
            tool_count=0,
            requires_auth=False,
            action_details=[],
            prompt_text="No pending action is available.",
            pin_attempts_remaining=None,
            pin_max_attempts=None,
        )

    action_details = []
    for call in tool_calls:
        tool_name = call.get("tool", "unknown")
        tool_input = call.get("tool_input") or {}
        summary = _tool_summary(tool_name, tool_input)
        action_details.append(summary)

    first_call = tool_calls[0]
    first_tool = first_call.get("tool", "unknown")
    first_summary = action_details[0] if action_details else "unknown action"

    if requires_auth:
        title = "Auth Required"
        prompt_text = f"High-risk action pending: {first_summary}"
        if len(tool_calls) > 1:
            prompt_text += f" and {len(tool_calls) - 1} more"
        prompt_text += ". Enter PIN to continue."
    else:
        title = "Confirm Action"
        prompt_text = f"Confirmation required: {first_summary}"
        if len(tool_calls) > 1:
            prompt_text += f" and {len(tool_calls) - 1} more"
        prompt_text += ". Reply yes to continue."

    return ConfirmationCard(
        title=title,
        description=first_summary,
        action_type=first_tool,
        tool_count=len(tool_calls),
        requires_auth=requires_auth,
        action_details=action_details,
        prompt_text=prompt_text,
        pin_attempts_remaining=(max(0, PIN_MAX_ATTEMPTS - pin_attempts) if requires_auth else None),
        pin_max_attempts=(PIN_MAX_ATTEMPTS if requires_auth else None),
    )


def build_pending_prompt(tool_calls: list[dict[str, Any]], requires_auth: bool) -> str:
    if not tool_calls:
        return "No pending action is available."
    first_call = tool_calls[0]
    tool_name = first_call.get("tool", "unknown")
    tool_input = first_call.get("tool_input") or {}
    summary = _tool_summary(tool_name, tool_input)
    if len(tool_calls) > 1:
        summary = f"{summary} (+{len(tool_calls) - 1})"
    if requires_auth:
        return f"High-risk action pending: {summary}. Enter PIN to continue."
    return f"Confirm action: {summary}. Reply yes to continue."


def register_pending_action(user_id: str, session_id: str, user_message: str, tool_calls: list[dict[str, Any]], requires_auth: bool) -> PendingAction:
    now = datetime.now(timezone.utc)
    pending = PendingAction(
        action_id=uuid4().hex,
        user_id=user_id,
        session_id=session_id,
        user_message=user_message,
        tool_calls=tool_calls,
        prompt=build_pending_prompt(tool_calls, requires_auth),
        requires_auth=requires_auth,
        created_at=now,
        expires_at=now + timedelta(seconds=config.assistant_action_timeout_seconds),
    )
    key = _pending_action_key(user_id, session_id)
    PENDING_ACTIONS[key] = pending
    return pending


def get_pending_action(user_id: str, session_id: str) -> PendingAction | None:
    key = _pending_action_key(user_id, session_id)
    pending = PENDING_ACTIONS.get(key)
    if not pending:
        return None
    if pending.expires_at <= datetime.now(timezone.utc):
        clear_pending_action(user_id, session_id)
        return None
    return pending


def clear_pending_action(user_id: str, session_id: str) -> None:
    key = _pending_action_key(user_id, session_id)
    PENDING_ACTIONS.pop(key, None)


def is_affirmative(message: str) -> bool:
    normalized = message.strip().lower()
    return normalized in {"yes", "y", "ok", "okay", "confirm", "confirmed", "approve", "approved", "proceed", "go", "go ahead", "do it", "continue"}


def is_negative(message: str) -> bool:
    normalized = message.strip().lower()
    return normalized in {"no", "n", "cancel", "stop", "abort", "never mind", "nevermind", "discard", "deny"}


def matches_assistant_pin(message: str) -> bool:
    pin = (config.assistant_action_pin or "").strip()
    if not pin:
        return False
    return message.strip() == pin


def requires_gate(tool_name: str) -> bool:
    policy = get_tool_policy(tool_name)
    return policy.requires_confirmation or policy.requires_auth


def requires_auth(tool_name: str) -> bool:
    return get_tool_policy(tool_name).requires_auth


def pin_attempts_remaining(pending: PendingAction) -> int:
    return max(0, PIN_MAX_ATTEMPTS - pending.pin_attempts)


def register_pin_rejection(pending: PendingAction) -> int:
    pending.pin_attempts += 1
    return pin_attempts_remaining(pending)
