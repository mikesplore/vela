from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, UTC
from typing import Any, Literal
from uuid import uuid4
from app.utils.config import get_config
from app.db.models import PendingAction
from app.domain.assistant import ConfirmationCard

config = get_config()

RiskLevel = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class ToolPolicy:
    risk_level: RiskLevel
    requires_confirmation: bool = False
    requires_auth: bool = False


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
    "get_currently_playing_song",
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
    "is_process_running",
    "list_installed_applications",
    "list_jobs",
    "cancel_job",
    "power_sleep",
    "get_service_status",
    "list_services",
    "list_failed_services",
    "list_timers",
    "check_package_installed",
    "get_boot_errors",
    "get_docker_info",
    "list_docker_containers",
    "get_container_status",
    "get_container_logs",
    "compose_status",
    "check_port",
    "health_check",
    "get_firewall_status",
    "get_vpn_status",
    "check_updates",
    "get_logs",
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
    "open_application",
    "close_application",
    "open_path",
    "rename_path",
    "schedule_job",
    "run_job_now",
    "make_directory",
    "zip_paths",
    "unzip_path",
    "start_service",
    "stop_service",
    "restart_service",
    "start_container",
    "stop_container",
    "restart_container",
    "send_push_notification",
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

PIN_MAX_ATTEMPTS = 3

# Initialize database on module load
from app.db.pending_actions import init_db, get_pending_action_from_db, save_pending_action, \
    delete_pending_action as db_delete_pending_action

init_db()


def _pending_action_key(user_id: str, session_id: str) -> str:
    """Generate a unique key for storing pending actions per user per session/device."""
    return f"{user_id}|{session_id}"


def get_tool_policy(tool_name: str) -> ToolPolicy:
    if tool_name in HIGH_RISK_TOOLS:
        return ToolPolicy(risk_level="high", requires_confirmation=False, requires_auth=True)
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


def build_confirmation_card(tool_calls: list[dict[str, Any]], requires_an_auth: bool,
                            pin_attempts: int = 0) -> ConfirmationCard:
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

    if requires_an_auth:
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
        requires_auth=requires_an_auth,
        action_details=action_details,
        prompt_text=prompt_text,
        pin_attempts_remaining=(max(0, PIN_MAX_ATTEMPTS - pin_attempts) if requires_an_auth else None),
        pin_max_attempts=(PIN_MAX_ATTEMPTS if requires_an_auth else None),
    )


from typing import Any

def build_pending_prompt(tool_calls: list[dict[str, Any]], requires_an_auth: bool) -> str:
    if not tool_calls:
        return "No actions pending."
    summaries = [
        _tool_summary(tc.get("tool") or "unknown", tc.get("tool_input") or {})
        for tc in tool_calls if tc  # 'if tc' protects against empty dicts/None elements
    ]

    valid_actions = [s for s in summaries if s and str(s).lower() != "none"]

    if not valid_actions:
        return "No actions pending."

    all_actions = ", ".join(valid_actions)

    if requires_an_auth:
        return f"To {all_actions}: Enter PIN to continue."
    return f"Confirm: {all_actions}? Reply yes to continue."


def register_pending_action(user_id: str, session_id: str, user_message: str, tool_calls: list[dict[str, Any]],
                            requires_auth: bool) -> PendingAction:
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
    # Save to database
    save_pending_action(pending)
    return pending


def get_pending_action(user_id: str, session_id: str) -> PendingAction | None:
    # Get from database
    pending = get_pending_action_from_db(user_id, session_id)
    if not pending:
        return None
    # Check expiration (also handled in DB function, but double-check here)
    expires_at = pending.expires_at
    if expires_at.tzinfo is None:
        # If stored as naive, assume UTC
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        clear_pending_action(user_id, session_id)
        return None
    return pending


def clear_pending_action(user_id: str, session_id: str) -> None:
    """Clear a pending action (used by both user cancellation and AI override)."""
    # Clear from database
    db_delete_pending_action(user_id, session_id)


def cancel_pending_action_by_ai(user_id: str, session_id: str, reason: str = "New request received") -> str:
    """
    Cancel a pending action initiated by the AI.
    Returns a message explaining the cancellation.
    """
    pending = get_pending_action_from_db(user_id, session_id)
    if pending:
        clear_pending_action(user_id, session_id)
        return f"Cancelled previous pending action: {reason}"
    return ""


def is_affirmative(message: str) -> bool:
    normalized = message.strip().lower()
    return normalized in {"yes", "y", "ok", "okay", "confirm", "confirmed", "approve", "approved", "proceed", "go",
                          "go ahead", "do it", "continue"}


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


def register_pin_rejection(pending: PendingAction) -> int:
    pending.pin_attempts += 1
    # Save updated pin attempts to database
    save_pending_action(pending)
    return max(0, PIN_MAX_ATTEMPTS - pending.pin_attempts)
