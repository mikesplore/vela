from typing import Any

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
        "description": "List connected Bluetooth devices and paired devices available to connect.",
    },
    "pair_bluetooth_device": {
        "method": "POST",
        "path": "/network/bluetooth/pair",
        "description": "Pair with a Bluetooth device.",
        "input": {"address": "string"},
    },
    "unpair_bluetooth_device": {
        "method": "POST",
        "path": "/network/bluetooth/unpair",
        "description": "Unpair a Bluetooth device.",
        "input": {"address": "string"},
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
    "get_monitor_state": {
        "method": "GET",
        "path": "/display/monitor/state",
        "description": "Read GNOME Mutter PowerSaveMode so the agent can see whether the monitor is on or off.",
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
        "description": "Current playback status, title, artist, album, album art URL, and position.",
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
        "description": "Capture the current screen with flameshot and return the PNG as base64.",
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
        "description": "Turn the monitor off using GNOME Mutter PowerSaveMode (with fallbacks).",
    },
    "monitor_on": {
        "method": "POST",
        "path": "/display/monitor/on",
        "description": "Turn the monitor on using GNOME Mutter PowerSaveMode (with fallbacks).",
    },
    "get_monitor_state": {
        "method": "GET",
        "path": "/display/monitor/state",
        "description": "Read the current GNOME Mutter PowerSaveMode so the agent can see whether the screen is on or off.",
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
        "description": "Type text at the current focused input.",
        "input": {"text": "string"},
    },
    "press_keyboard_keys": {
        "method": "POST",
        "path": "/input/keyboard/key",
        "description": "Press one or more keyboard keys or shortcuts.",
        "input": {"keys": "array of strings"},
    },
    # ── Process control ───────────────────────────────────────────────────────
    "list_processes": {
        "method": "GET",
        "path": "/processes/list",
        "description": "List running processes.",
    },
    "kill_process": {
        "method": "POST",
        "path": "/processes/kill",
        "description": "Kill a process by PID.",
        "input": {"pid": "integer"},
    },
    "kill_process_by_name": {
        "method": "POST",
        "path": "/processes/kill/{name}",
        "description": "Kill all processes matching a name.",
        "input": {"name": "string"},
    },
    # ── System power ──────────────────────────────────────────────────────────
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

_TOOL_LIST = "\n".join(
    "- " + name + ": " + t["description"] + (f" | input: {t['input']}" if "input" in t else "")
    for name, t in TOOL_DEFINITIONS.items()
)

SYSTEM_TOOL_PROMPT = f"""You are a JSON-only tool router. Your ONLY job is to select tools from the list below and return a JSON array.

CRITICAL RULES:
1. You MUST respond with ONLY a JSON array. No markdown, no explanations, no natural language.
2. Your response must start with '[' and end with ']'.
3. For ANY user message — including greetings, questions, or conversation — you must return a JSON array.
4. Even for "thank you" or casual chat, return: [{{"tool":"none","tool_input":{{}},"conversational_reply":"You're welcome!"}}]
5. NEVER output plain text like "**Battery Status**" or "Your battery is at 83%".

Valid response formats:
- Single tool: [{{"tool":"get_battery","tool_input":{{}}}}]
- Multiple tools: [{{"tool":"set_volume","tool_input":{{"value":40}}}},{{"tool":"lock_session","tool_input":{{}}}}]
- Conversation: [{{"tool":"none","tool_input":{{}},"conversational_reply":"Your reply here"}}]

Available tools:
{_TOOL_LIST}

REMEMBER: Output ONLY the JSON array. Nothing else."""
