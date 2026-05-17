import asyncio
import base64
import json
import logging
import os
import re
from typing import Any
from urllib.parse import quote_plus

import dashscope
from dashscope import Generation
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from pydantic import BaseModel

from config import Config
from dependencies import get_current_user

config = Config()
router = APIRouter(prefix="/assistant", tags=["assistant"])
logger = logging.getLogger("vela.assistant")

# In-memory session store: {user_id: [{"role": "user|assistant", "content": "..."}, ...]}
SESSION_STORE: dict[str, list[dict[str, str]]] = {}
MAX_HISTORY_CHARS = 4000  # Token-budget-aware trimming instead of message count

# ---------------------------------------------------------------------------
# Tool definitions — single source of truth.
# "response" key kept here for internal docs but NOT sent to the model.
# ---------------------------------------------------------------------------
TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {
    # ── System info ──────────────────────────────────────────────────────────
    "get_system_info": {
        "method": "GET",
        "path": "/system/info",
        "description": "Full system snapshot: CPU, RAM, GPU, disk, OS, USB, monitors, BIOS.",
    },
    "get_system_cpu": {
        "method": "GET",
        "path": "/system/cpu",
        "description": "CPU model, core counts, base frequency, architecture.",
    },
    "get_system_ram": {
        "method": "GET",
        "path": "/system/ram",
        "description": "RAM and swap usage statistics.",
    },
    "get_system_gpu": {
        "method": "GET",
        "path": "/system/gpu",
        "description": "Detected GPU devices.",
    },
    "get_system_disk": {
        "method": "GET",
        "path": "/system/disk",
        "description": "Disk partition usage information.",
    },
    "get_system_os": {
        "method": "GET",
        "path": "/system/os",
        "description": "OS name, kernel, hostname, user, and uptime.",
    },
    "get_system_usb": {
        "method": "GET",
        "path": "/system/usb",
        "description": "Connected USB devices.",
    },
    "get_system_monitors": {
        "method": "GET",
        "path": "/system/monitors",
        "description": "Connected monitor details.",
    },
    "get_system_bios": {
        "method": "GET",
        "path": "/system/bios",
        "description": "BIOS vendor, version, release date, and motherboard.",
    },
    # ── Network ──────────────────────────────────────────────────────────────
    "get_network_ip": {
        "method": "GET",
        "path": "/network/ip",
        "description": "Local and public IP addresses.",
    },
    "get_network_location": {
        "method": "GET",
        "path": "/network/location",
        "description": "Public IP with geo-location: city, region, country, timezone, ISP, coordinates.",
    },
    "get_wifi_status": {
        "method": "GET",
        "path": "/network/wifi/status",
        "description": "Current WiFi connection status and available networks.",
    },
    "list_wifi_networks": {
        "method": "GET",
        "path": "/network/wifi/list",
        "description": "List available WiFi networks.",
    },
    "connect_wifi": {
        "method": "POST",
        "path": "/network/wifi/connect",
        "description": "Connect to a WiFi network.",
        "input": {"ssid": "string", "password": "string?"},
    },
    "disconnect_wifi": {
        "method": "POST",
        "path": "/network/wifi/disconnect",
        "description": "Disconnect from the current WiFi network.",
    },
    "toggle_wifi": {
        "method": "POST",
        "path": "/network/wifi/toggle",
        "description": "Enable or disable the WiFi radio.",
        "input": {"enabled": "boolean"},
    },
    "list_bluetooth_devices": {
        "method": "GET",
        "path": "/network/bluetooth/devices",
        "description": "List paired and available Bluetooth devices.",
    },
    "toggle_bluetooth": {
        "method": "POST",
        "path": "/network/bluetooth/toggle",
        "description": "Enable or disable the Bluetooth radio.",
        "input": {"enabled": "boolean"},
    },
    "ping_host": {
        "method": "POST",
        "path": "/network/ping",
        "description": "Ping a host and return packet loss and average RTT.",
        "input": {"host": "string", "count": "integer 1-20"},
    },
    # ── Monitor / live metrics ────────────────────────────────────────────────
    "get_snapshot": {
        "method": "GET",
        "path": "/monitor/snapshot",
        "description": "Live metrics snapshot: CPU, RAM, GPU, disk I/O, network I/O, temps, fans, battery, processes.",
    },
    "monitor_cpu": {
        "method": "GET",
        "path": "/monitor/cpu",
        "description": "CPU usage percentages overall and per core.",
    },
    "monitor_ram": {
        "method": "GET",
        "path": "/monitor/ram",
        "description": "RAM and swap usage status.",
    },
    "monitor_gpu": {
        "method": "GET",
        "path": "/monitor/gpu",
        "description": "GPU utilization and memory usage.",
    },
    "monitor_disk_io": {
        "method": "GET",
        "path": "/monitor/disk-io",
        "description": "Per-disk I/O rates.",
    },
    "monitor_network_io": {
        "method": "GET",
        "path": "/monitor/network-io",
        "description": "Network I/O rates per interface.",
    },
    "monitor_temperatures": {
        "method": "GET",
        "path": "/monitor/temperatures",
        "description": "Sensor temperature readings.",
    },
    "monitor_fans": {
        "method": "GET",
        "path": "/monitor/fans",
        "description": "Fan speed sensor readings.",
    },
    "get_battery": {
        "method": "GET",
        "path": "/monitor/battery",
        "description": "Battery percentage, plugged state, and remaining seconds.",
    },
    "get_top_processes": {
        "method": "GET",
        "path": "/monitor/processes",
        "description": "Top processes by CPU and memory.",
    },
    # ── Audio / volume ────────────────────────────────────────────────────────
    "get_volume": {
        "method": "GET",
        "path": "/audio/volume",
        "description": "Current master volume level and mute state.",
    },
    "set_volume": {
        "method": "POST",
        "path": "/audio/volume",
        "description": "Set audio volume to a specific percentage.",
        "input": {"value": "integer 0-100"},
    },
    "volume_up": {
        "method": "POST",
        "path": "/audio/volume/up",
        "description": "Increase the master volume by a step.",
        "input": {"step": "integer 1-20"},
    },
    "volume_down": {
        "method": "POST",
        "path": "/audio/volume/down",
        "description": "Decrease the master volume by a step.",
        "input": {"step": "integer 1-20"},
    },
    "mute_audio": {
        "method": "POST",
        "path": "/audio/mute",
        "description": "Mute or unmute the master audio channel.",
        "input": {"muted": "boolean"},
    },
    "audio_devices": {
        "method": "GET",
        "path": "/audio/devices",
        "description": "List available audio sinks and sources.",
    },
    "set_output_device": {
        "method": "POST",
        "path": "/audio/output-device",
        "description": "Switch the default audio output device.",
        "input": {"device_id": "string"},
    },
    # ── Media playback ────────────────────────────────────────────────────────
    "get_media_status": {
        "method": "GET",
        "path": "/media/now-playing",
        "description": "Current playback status, title, artist, album, and position.",
    },
    "toggle_play_pause": {
        "method": "POST",
        "path": "/media/play-pause",
        "description": "Toggle media playback on or off.",
    },
    "next_track": {
        "method": "POST",
        "path": "/media/next",
        "description": "Skip to the next media track.",
    },
    "previous_track": {
        "method": "POST",
        "path": "/media/previous",
        "description": "Skip to the previous media track.",
    },
    "seek_media": {
        "method": "POST",
        "path": "/media/seek",
        "description": "Seek media playback to a position in seconds.",
        "input": {"seconds": "number"},
    },
    # ── Clipboard ─────────────────────────────────────────────────────────────
    "read_clipboard": {
        "method": "GET",
        "path": "/clipboard/read",
        "description": "Read the current clipboard text.",
    },
    "write_clipboard": {
        "method": "POST",
        "path": "/clipboard/write",
        "description": "Write text to the clipboard.",
        "input": {"text": "string"},
    },
    "clear_clipboard": {
        "method": "POST",
        "path": "/clipboard/clear",
        "description": "Clear the clipboard contents.",
    },
    # ── Display ───────────────────────────────────────────────────────────────
    "display_screenshot": {
        "method": "GET",
        "path": "/display/screenshot",
        "description": "Capture the current screen and return a PNG as base64.",
    },
    "display_record": {
        "method": "POST",
        "path": "/display/record",
        "description": "Record a short screen clip and return MP4 as base64.",
        "input": {"duration_seconds": "integer 1-60"},
    },
    "monitor_off": {
        "method": "POST",
        "path": "/display/monitor/off",
        "description": "Turn the monitor off.",
    },
    "monitor_on": {
        "method": "POST",
        "path": "/display/monitor/on",
        "description": "Turn the monitor on.",
    },
    "get_display_brightness": {
        "method": "GET",
        "path": "/display/brightness",
        "description": "Get the current screen brightness.",
    },
    "set_display_brightness": {
        "method": "POST",
        "path": "/display/brightness",
        "description": "Set the screen brightness.",
        "input": {"value": "integer 0-100"},
    },
    "get_resolution": {
        "method": "GET",
        "path": "/display/resolution",
        "description": "Get the current display resolution and refresh rate.",
    },
    "set_resolution": {
        "method": "POST",
        "path": "/display/resolution",
        "description": "Set the display resolution and refresh rate.",
        "input": {"width": "integer", "height": "integer", "refresh": "integer"},
    },
    "rotate_display": {
        "method": "POST",
        "path": "/display/rotate",
        "description": "Rotate the display orientation.",
        "input": {"orientation": "normal|left|right|inverted"},
    },
    "lock_screen_display": {
        "method": "POST",
        "path": "/display/lock",
        "description": "Lock the screen session.",
    },
    "set_night_light": {
        "method": "POST",
        "path": "/display/night-light",
        "description": "Enable or disable night light and set colour temperature.",
        "input": {"enabled": "boolean", "temperature": "integer"},
    },
    # ── Filesystem ────────────────────────────────────────────────────────────
    "list_files": {
        "method": "GET",
        "path": "/fs/list",
        "description": "List files and directories at a path.",
        "input": {"path": "string"},
    },
    "download_file": {
        "method": "GET",
        "path": "/fs/download",
        "description": "Download a file from the filesystem.",
        "input": {"path": "string"},
    },
    "upload_file": {
        "method": "POST",
        "path": "/fs/upload",
        "description": "Upload a file to a destination path.",
        "input": {"path": "string", "file_base64": "string"},
    },
    "delete_path": {
        "method": "DELETE",
        "path": "/fs/delete",
        "description": "Delete a file or directory.",
        "input": {"path": "string"},
    },
    "make_directory": {
        "method": "POST",
        "path": "/fs/mkdir",
        "description": "Create a new directory.",
        "input": {"path": "string"},
    },
    "rename_path": {
        "method": "POST",
        "path": "/fs/rename",
        "description": "Rename or move a file or directory.",
        "input": {"from": "string", "to": "string"},
    },
    "search_files": {
        "method": "GET",
        "path": "/fs/search",
        "description": "Search files and directories by name.",
        "input": {"query": "string", "path": "string"},
    },
    "get_disk_usage": {
        "method": "GET",
        "path": "/fs/disk-usage",
        "description": "Disk usage statistics for mounted partitions.",
    },
    "zip_paths": {
        "method": "POST",
        "path": "/fs/zip",
        "description": "Create a zip archive from files and directories.",
        "input": {"paths": "array of strings", "output": "string"},
    },
    "unzip_path": {
        "method": "POST",
        "path": "/fs/unzip",
        "description": "Extract a zip archive to a destination directory.",
        "input": {"path": "string", "destination": "string"},
    },
    "open_path": {
        "method": "POST",
        "path": "/fs/open",
        "description": "Open a file or directory with the default system application.",
        "input": {"path": "string"},
    },
    # ── Input control ─────────────────────────────────────────────────────────
    "move_mouse": {
        "method": "POST",
        "path": "/input/mouse/move",
        "description": "Move the mouse cursor to given coordinates.",
        "input": {"x": "integer", "y": "integer"},
    },
    "click_mouse": {
        "method": "POST",
        "path": "/input/mouse/click",
        "description": "Click the mouse at given coordinates.",
        "input": {"x": "integer", "y": "integer", "button": "left|right|middle"},
    },
    "double_click_mouse": {
        "method": "POST",
        "path": "/input/mouse/double-click",
        "description": "Double-click the mouse at given coordinates.",
        "input": {"x": "integer", "y": "integer"},
    },
    "scroll_mouse": {
        "method": "POST",
        "path": "/input/mouse/scroll",
        "description": "Scroll the mouse wheel up or down.",
        "input": {"direction": "up|down", "amount": "integer"},
    },
    "type_keyboard": {
        "method": "POST",
        "path": "/input/keyboard/type",
        "description": "Type text using the keyboard.",
        "input": {"text": "string"},
    },
    "press_keyboard_keys": {
        "method": "POST",
        "path": "/input/keyboard/key",
        "description": "Press a keyboard key or key combination.",
        "input": {"keys": "array of strings"},
    },
    # ── Processes / windows ───────────────────────────────────────────────────
    "list_processes": {
        "method": "GET",
        "path": "/processes",
        "description": "List running processes with CPU and memory usage.",
    },
    "kill_process": {
        "method": "DELETE",
        "path": "/processes/{pid}",
        "description": "Terminate a process by PID.",
        "input": {"pid": "integer"},
    },
    "kill_process_by_name": {
        "method": "DELETE",
        "path": "/processes/name/{name}",
        "description": "Terminate all processes matching a name.",
        "input": {"name": "string"},
    },
    "launch_process": {
        "method": "POST",
        "path": "/processes/launch",
        "description": "Launch a new process with optional arguments.",
        "input": {"command": "string", "args": "array of strings"},
    },
    "active_window": {
        "method": "GET",
        "path": "/processes/active-window",
        "description": "Return the currently focused window title.",
    },
    "minimize_window": {
        "method": "POST",
        "path": "/processes/window/minimize",
        "description": "Minimize a window by ID.",
        "input": {"window_id": "string"},
    },
    "close_window": {
        "method": "POST",
        "path": "/processes/window/close",
        "description": "Close a window by ID.",
        "input": {"window_id": "string"},
    },
    # ── Security ──────────────────────────────────────────────────────────────
    "lock_session": {
        "method": "POST",
        "path": "/security/lock",
        "description": "Lock the screen session.",
    },
    "logout_user": {
        "method": "POST",
        "path": "/security/logout",
        "description": "Log out the current user session.",
    },
    "disable_webcam": {
        "method": "POST",
        "path": "/security/webcam/disable",
        "description": "Disable the webcam.",
    },
    "enable_webcam": {
        "method": "POST",
        "path": "/security/webcam/enable",
        "description": "Enable the webcam.",
    },
    "webcam_snapshot": {
        "method": "POST",
        "path": "/security/webcam/snapshot",
        "description": "Capture a webcam image and return it as base64.",
    },
    "disable_mic": {
        "method": "POST",
        "path": "/security/mic/disable",
        "description": "Disable the default microphone.",
    },
    "enable_mic": {
        "method": "POST",
        "path": "/security/mic/enable",
        "description": "Enable the default microphone.",
    },
    "get_login_history": {
        "method": "GET",
        "path": "/security/login-history",
        "description": "Recent login history events.",
    },
    "get_ssh_sessions": {
        "method": "GET",
        "path": "/security/ssh-sessions",
        "description": "Active SSH sessions.",
    },
    # ── Maintenance ───────────────────────────────────────────────────────────
    "clear_cache": {
        "method": "POST",
        "path": "/maintenance/clear-cache",
        "description": "Clear temporary and user cache directories.",
    },
    "get_logs": {
        "method": "GET",
        "path": "/maintenance/logs",
        "description": "Get the last N lines of a service journal log.",
        "input": {"service": "string", "lines": "integer"},
    },
    "check_updates": {
        "method": "GET",
        "path": "/maintenance/updates",
        "description": "Check for available system package updates.",
    },
    "run_update": {
        "method": "POST",
        "path": "/maintenance/update",
        "description": "Run a full system update after explicit confirmation.",
        "input": {"confirm": "boolean"},
    },
    "sync_time": {
        "method": "POST",
        "path": "/maintenance/sync-time",
        "description": "Sync the system clock via NTP.",
    },
    "list_services": {
        "method": "GET",
        "path": "/maintenance/services",
        "description": "List systemd services and their status.",
    },
    "restart_service": {
        "method": "POST",
        "path": "/maintenance/service/restart",
        "description": "Restart a systemd service.",
        "input": {"name": "string"},
    },
    "stop_service": {
        "method": "POST",
        "path": "/maintenance/service/stop",
        "description": "Stop a systemd service.",
        "input": {"name": "string"},
    },
    "start_service": {
        "method": "POST",
        "path": "/maintenance/service/start",
        "description": "Start a systemd service.",
        "input": {"name": "string"},
    },
    # ── Notifications ─────────────────────────────────────────────────────────
    "send_notification": {
        "method": "POST",
        "path": "/notifications/send",
        "description": "Send a desktop notification.",
        "input": {"title": "string", "message": "string", "app_name": "string?", "urgency": "low|normal|critical?"},
    },
    "clear_notifications": {
        "method": "POST",
        "path": "/notifications/clear",
        "description": "Clear agent-tracked and desktop notifications.",
    },
    "read_notifications": {
        "method": "GET",
        "path": "/notifications/read",
        "description": "Read notifications sent through this agent.",
    },
    "list_notifications": {
        "method": "GET",
        "path": "/notifications/list",
        "description": "List desktop notification history.",
    },
    # ── Power ─────────────────────────────────────────────────────────────────
    "power_shutdown": {
        "method": "POST",
        "path": "/power/shutdown",
        "description": "Shut down the machine.",
    },
    "power_restart": {
        "method": "POST",
        "path": "/power/restart",
        "description": "Restart the machine.",
    },
    "power_sleep": {
        "method": "POST",
        "path": "/power/sleep",
        "description": "Put the machine to sleep.",
    },
    "power_hibernate": {
        "method": "POST",
        "path": "/power/hibernate",
        "description": "Hibernate the machine.",
    },
    # ── Scheduler ─────────────────────────────────────────────────────────────
    "schedule_job": {
        "method": "POST",
        "path": "/scheduler/create",
        "description": "Schedule a command at a specific time or on a cron schedule.",
        "input": {"command": "string", "args": "array of strings", "run_at": "ISO datetime", "recurring": "string?"},
    },
    "list_jobs": {
        "method": "GET",
        "path": "/scheduler/list",
        "description": "List all scheduled tasks.",
    },
    "cancel_job": {
        "method": "DELETE",
        "path": "/scheduler/cancel/{task_id}",
        "description": "Cancel a scheduled task.",
        "input": {"task_id": "string"},
    },
    "run_job_now": {
        "method": "POST",
        "path": "/scheduler/run-now/{task_id}",
        "description": "Trigger a scheduled task immediately.",
        "input": {"task_id": "string"},
    },
}

INPUT_CONFIRM_TOOLS = {
    "move_mouse",
    "click_mouse",
    "double_click_mouse",
    "scroll_mouse",
    "type_keyboard",
    "press_keyboard_keys",
}

# ---------------------------------------------------------------------------
# Prompts — built once at module load.
# Response shapes intentionally excluded from the tool list to save tokens.
# ---------------------------------------------------------------------------
_TOOL_LIST = "\n".join(
    "- " + name + ": " + t["description"] + (f" | input: {t['input']}" if "input" in t else "")
    for name, t in TOOL_DEFINITIONS.items()
)

# The model ALWAYS returns a JSON array — even for a single tool or a
# conversational reply. This is what enables multi-tool parallel execution.
SYSTEM_TOOL_PROMPT = f"""You are Vela, a friendly Linux PC assistant focused on PC control and system management. Always reply with valid JSON only — no extra text. Use emoji where appropriate. Be concise.

Always return a JSON ARRAY of tool calls, even for a single action:
[{{"tool":"<tool_name>","tool_input":{{...}}}}, ...]

For multiple simultaneous actions, include all of them in the array:
[{{"tool":"set_volume","tool_input":{{"value":40}}}},{{"tool":"lock_session","tool_input":{{}}}}]

For casual conversation or out-of-scope questions, return a single-item array:
[{{"tool":"none","tool_input":{{}},"conversational_reply":"<your reply>"}}]

IMPORTANT — DO NOT answer general knowledge questions unrelated to PC control. For those, return:
[{{"tool":"none","tool_input":{{}},"conversational_reply":"I only manage your Linux PC! Ask me about files, volume, processes, or system stats 🐧"}}]

Available tools:
{_TOOL_LIST}"""


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class AssistantRequest(BaseModel):
    message: str


class AssistantResponse(BaseModel):
    reply: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _dict_get(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _clean_text(text: str) -> str:
    """Strip markdown code fences that some models wrap around JSON."""
    if not text:
        return ""
    cleaned = text.strip()
    cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*```$', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _get_api_key() -> str | None:
    return (
        config.dashscope_api_key
        or os.getenv("DASHSCOPE_API_KEY")
        or os.getenv("VELA_DASHSCOPE_API_KEY")
    )


def _get_response_text(response_data: Any) -> str:
    if response_data is None:
        return ""
    output = _dict_get(response_data, "output")
    if output is not None:
        text = _dict_get(output, "text")
        if text:
            return _clean_text(str(text))
        choices = _dict_get(output, "choices") or []
        if isinstance(choices, dict):
            choices = [choices]
        for choice in choices:
            if choice is None:
                continue
            message = _dict_get(choice, "message")
            if not message:
                continue
            content = _dict_get(message, "content") or _dict_get(message, "text")
            if content:
                return _clean_text(str(content))
    if isinstance(response_data, dict):
        return _clean_text(json.dumps(response_data))
    return _clean_text(str(response_data))


def _set_dashscope_base_url() -> None:
    """Resolve and set the DashScope base URL. Called once at startup."""
    api_url = (
        os.getenv("DASHSCOPE_HTTP_BASE_URL")
        or os.getenv("DASHSCOPE_API_URL")
        or os.getenv("VELA_DASHSCOPE_API_URL")
        or config.dashscope_api_url
    )
    if "/chat/completions" in api_url:
        api_url = api_url.split("/chat/completions")[0]
    if api_url.startswith("https://api.dashscope.com"):
        api_url = api_url.replace("https://api.dashscope.com", "https://dashscope-intl.aliyuncs.com/api")
    if api_url.startswith("https://dashscope-intl.aliyuncs.com/v1"):
        api_url = api_url.replace("https://dashscope-intl.aliyuncs.com/v1", "https://dashscope-intl.aliyuncs.com/api/v1")
    dashscope.base_http_api_url = api_url.rstrip("/")


# Set once at import time — not on every request.
_set_dashscope_base_url()


def _extract_json_array(text: str) -> list[dict[str, Any]] | None:
    """
    Extract a JSON array from the model's response.
    Falls back to wrapping a single object in a list for robustness.
    """
    cleaned = _clean_text(text)

    # Primary: look for an array
    match = re.search(r"\[.*\]", cleaned, flags=re.DOTALL)
    if match:
        candidate = match.group(0)
        try:
            result = json.loads(candidate)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            try:
                candidate = re.sub(r",\s*\]\s*$", "]", candidate)
                candidate = re.sub(r",\s*}\s*]", "}]", candidate)
                result = json.loads(candidate)
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass

    # Fallback: single object → wrap in list
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        try:
            obj = json.loads(match.group(0))
            if isinstance(obj, dict) and "tool" in obj:
                return [obj]
        except json.JSONDecodeError:
            pass

    return None


# ---------------------------------------------------------------------------
# Session management — trimmed by character budget, not message count.
# ---------------------------------------------------------------------------
def _get_or_init_session(user_id: str) -> list[dict[str, str]]:
    if user_id not in SESSION_STORE:
        SESSION_STORE[user_id] = []
    return SESSION_STORE[user_id]


def _trim_history(history: list[dict[str, str]], max_chars: int = MAX_HISTORY_CHARS) -> list[dict[str, str]]:
    """Keep the most recent messages that fit within max_chars."""
    total = 0
    trimmed: list[dict[str, str]] = []
    for msg in reversed(history):
        total += len(msg["content"])
        if total > max_chars:
            break
        trimmed.insert(0, msg)
    return trimmed


# ---------------------------------------------------------------------------
# LLM calls
# ---------------------------------------------------------------------------
def _plan_tool_calls(user_message: str, history: list[dict[str, str]] | None = None) -> list[dict[str, Any]]:
    """
    Single LLM call → list of tool calls to execute in parallel.
    For conversational replies returns a single-item list with tool="none".
    Token cost is the same whether the user asks for 1 or 5 simultaneous actions.
    """
    messages = [{"role": "system", "content": SYSTEM_TOOL_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    response = Generation.call(
        api_key=_get_api_key(),
        model=config.dashscope_model,
        messages=messages,
        result_format="message",
        stream=False,
        incremental_output=False,
        temperature=0.0,
        max_tokens=512,
    )
    text = _get_response_text(response)
    parsed = _extract_json_array(text)
    if not parsed:
        raise ValueError(f"Could not parse tool selection from model output: {text}")
    return parsed


def _compose_final_reply(user_message: str, results: list[dict[str, Any]]) -> str:
    """
    Second LLM call — summarises ALL tool results into one clean Markdown reply.
    Called only when at least one real tool was executed.
    """
    system = (
        "You are Vela. The user asked for one or more actions. "
        "Use the tool results below to write a single concise Markdown reply. "
        "Do not return raw JSON. If any action failed, say so clearly."
    )
    results_text = "\n".join(
        f"Tool: {r['tool']}\nResult: {json.dumps(r['result'], separators=(',', ':'))}"
        + (f"\nError: {r['error']}" if r.get("error") else "")
        for r in results
    )
    response = Generation.call(
        api_key=_get_api_key(),
        model=config.dashscope_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"User request: {user_message}\n\n{results_text}\n\nAnswer in clean Markdown."},
        ],
        result_format="message",
        stream=False,
        incremental_output=False,
        temperature=0.2,
        max_tokens=512,
    )
    return _get_response_text(response)


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------
async def _execute_tool(
    app: FastAPI,
    tool_name: str,
    tool_input: dict[str, Any],
    auth_header: str | None,
) -> dict[str, Any]:
    if tool_name not in TOOL_DEFINITIONS:
        raise ValueError(f"Unknown tool: {tool_name}")

    tool = TOOL_DEFINITIONS[tool_name]
    path = tool["path"]

    if tool_name == "kill_process_by_name":
        name = tool_input.get("name")
        if not name:
            raise ValueError("tool_input.name is required for kill_process_by_name")
        path = path.format(name=quote_plus(str(name)))
        tool_input = {}

    headers: dict[str, str] = {}
    if tool_name != "upload_file":
        headers["Content-Type"] = "application/json"
    if tool_name in INPUT_CONFIRM_TOOLS:
        headers["X-Confirm-Input"] = "true"
    if auth_header:
        headers["Authorization"] = auth_header

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        method = tool["method"].upper()
        if tool_name == "upload_file":
            file_base64 = tool_input.get("file_base64")
            path_value = tool_input.get("path")
            if not path_value or not file_base64:
                raise ValueError("tool_input.path and tool_input.file_base64 are required for upload_file")
            response = await client.post(
                path,
                data={"path": path_value},
                files={"file": ("upload.bin", base64.b64decode(file_base64), "application/octet-stream")},
                headers=headers,
                timeout=20.0,
            )
        elif method == "GET":
            response = await client.get(path, params=tool_input or {}, headers=headers, timeout=20.0)
        else:
            response = await client.request(method, path, json=tool_input or {}, headers=headers, timeout=20.0)

    if tool_name == "download_file":
        if response.status_code >= 400:
            try:
                error_data = response.json()
            except ValueError:
                error_data = response.text
            raise ValueError(f"Tool {tool_name} failed: {response.status_code} {error_data}")
        return {
            "path": tool_input.get("path"),
            "content_base64": base64.b64encode(response.content).decode("utf-8"),
            "content_type": response.headers.get("content-type", "application/octet-stream"),
        }

    try:
        data = response.json()
    except ValueError:
        raise ValueError(f"Tool {tool_name} returned invalid JSON: {response.text}")

    if response.status_code >= 400:
        raise ValueError(f"Tool {tool_name} failed: {response.status_code} {data}")
    return data


async def _execute_tool_safe(
    app: FastAPI,
    tool_name: str,
    tool_input: dict[str, Any],
    auth_header: str | None,
) -> dict[str, Any]:
    """Wrapper that catches errors so one failing tool doesn't abort the others."""
    try:
        result = await _execute_tool(app, tool_name, tool_input, auth_header)
        return {"tool": tool_name, "result": result, "error": None}
    except Exception as exc:
        logger.error("Tool %s failed: %s", tool_name, exc, exc_info=True)
        return {"tool": tool_name, "result": {}, "error": str(exc)}


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------
@router.post("/chat", response_model=AssistantResponse, dependencies=[Depends(get_current_user)])
async def chat(
    body: AssistantRequest,
    request: Request,
    current_user: str = Depends(get_current_user),
) -> AssistantResponse:
    auth_header = request.headers.get("authorization")
    history = _get_or_init_session(current_user)

    history.append({"role": "user", "content": body.message})
    history = _trim_history(history)

    # --- Step 1: one LLM call → list of tool calls (1 or many) --------------
    try:
        tool_calls = _plan_tool_calls(body.message, history[:-1])
    except Exception as exc:
        logger.error("Tool planning failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail=str(exc))

    # --- Step 2: dispatch ----------------------------------------------------
    if len(tool_calls) == 1 and tool_calls[0].get("tool") == "none":
        # Conversational reply — already inline, zero extra LLM calls.
        reply_text: str = tool_calls[0].get("conversational_reply") or "Hello! How can I help you today?"
    else:
        # Execute all real tools concurrently — one asyncio round-trip,
        # regardless of how many tools were requested.
        tasks = [
            _execute_tool_safe(request.app, tc["tool"], tc.get("tool_input") or {}, auth_header)
            for tc in tool_calls
            if tc.get("tool") and tc["tool"] != "none"
        ]
        tool_results = list(await asyncio.gather(*tasks))

        try:
            reply_text = _compose_final_reply(body.message, tool_results)
        except Exception as exc:
            logger.error("Final response composition failed: %s", exc, exc_info=True)
            # Graceful fallback: plain bullet list of raw results
            reply_text = "\n".join(
                f"- **{r['tool']}**: {r['error'] or json.dumps(r['result'], separators=(',', ':'))}"
                for r in tool_results
            )

    # --- Persist updated history ---------------------------------------------
    reply_text = reply_text.strip()
    history.append({"role": "assistant", "content": reply_text})
    SESSION_STORE[current_user] = _trim_history(history)

    return AssistantResponse(reply=reply_text)