from typing import Any

TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {
    # ── System info ──────────────────────────────────────────────────────────
    "get_system_info": {
        "method": "GET",
        "path": "/system/info",
        "description": "Static hardware specs bundle: CPU model, RAM capacity, GPU model, disk partitions, OS version, USB devices, monitor config, and BIOS. Use when the user wants to know WHAT their machine is made of. Do NOT use for live usage — use get_snapshot for live metrics.",
    },
    "get_system_cpu": {
        "method": "GET",
        "path": "/system/cpu",
        "description": "Static CPU specs: model name, core/thread counts, base clock, architecture. Use when the user asks WHAT CPU they have. Do NOT use for live CPU load — use monitor_cpu for current usage.",
    },
    "get_system_ram": {
        "method": "GET",
        "path": "/system/ram",
        "description": "Static RAM capacity: total installed memory and swap size. Use when the user asks how much RAM they have. Do NOT use for live memory usage — use monitor_ram for that.",
    },
    "get_system_gpu": {
        "method": "GET",
        "path": "/system/gpu",
        "description": "Static GPU info: GPU device names and models. Use when the user asks WHAT GPU they have. Do NOT use for live GPU load — use monitor_gpu for that.",
    },
    "get_system_disk": {
        "method": "GET",
        "path": "/system/disk",
        "description": "Static disk layout: partition names, mount points, filesystem types, and total sizes. Use when the user asks about drive partitions or disk setup. Do NOT use for free space or usage stats — use get_disk_usage for that.",
    },
    "get_system_os": {
        "method": "GET",
        "path": "/system/os",
        "description": "OS identity: distro name, kernel version, hostname, current username. Use for OS/kernel-specific questions. For a full device summary including hardware vendor and model, use get_device_info instead.",
    },
    "get_system_usb": {
        "method": "GET",
        "path": "/system/usb",
        "description": "Connected USB devices.",
    },
    "get_system_monitors": {
        "method": "GET",
        "path": "/system/monitors",
        "description": "Static monitor hardware info: display names, resolutions, refresh rates. Use when the user asks about their monitor specs. Do NOT use to check if the monitor is on/off — use get_monitor_state for that.",
    },
    "get_system_bios": {
        "method": "GET",
        "path": "/system/bios",
        "description": "BIOS vendor, version, release date, and motherboard.",
    },
    "get_device_info": {
        "method": "GET",
        "path": "/system/device",
        "description": "High-level device identity: laptop model (e.g. ThinkPad X1 Carbon Gen 9), vendor (e.g. Lenovo), OS distro, kernel, architecture, hostname. Use when the user asks 'what device/laptop/computer is this'. For deeper hardware specs use get_system_info; for OS-only details use get_system_os.",
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
        "description": "Current WiFi connection state only: connected/disconnected, active SSID, signal strength. Use when the user asks if they are connected or what network they are on. Do NOT use to browse nearby networks — use list_wifi_networks for that.",
    },
    "list_wifi_networks": {
        "method": "GET",
        "path": "/network/wifi/list",
        "description": "Scan and list all nearby WiFi networks with SSID and signal strength. Use when the user wants to see what networks are available nearby, not just their current connection.",
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
        "description": "Live system metrics snapshot: current CPU load, RAM usage, GPU usage, disk I/O rates, network I/O rates, temperatures, fan speeds, battery level, top processes. Use for 'how is my PC doing' or real-time status. Do NOT use for static hardware specs — use get_system_info for that.",
    },
    "monitor_cpu": {
        "method": "GET",
        "path": "/monitor/cpu",
        "description": "Live CPU usage: current load percentage overall and per core. Use when the user asks how loaded their CPU is right now. Do NOT use for CPU specs or model — use get_system_cpu for that.",
    },
    "monitor_ram": {
        "method": "GET",
        "path": "/monitor/ram",
        "description": "Live memory usage: how much RAM and swap is currently used vs free. Use when the user asks how much memory is being used right now. Do NOT use for total RAM capacity — use get_system_ram for that.",
    },
    "monitor_gpu": {
        "method": "GET",
        "path": "/monitor/gpu",
        "description": "Live GPU usage: current GPU utilization percentage and VRAM used. Use when the user asks how hard their GPU is working right now. Do NOT use for GPU model info — use get_system_gpu for that.",
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
        "description": "Top resource-consuming processes ranked by CPU and memory usage. Use when the user asks what is slowing down or eating up their system. Do NOT use to find a specific process by name — use list_processes for that.",
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
    "get_currently_playing_song": {
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
        "description": "Capture the current screen with flameshot to ~/Pictures. Returns a confirmation that the screenshot was taken. The image is sent to the user interface (not to the AI model), so the AI model never receives the image binary — it just gets a success confirmation. Do NOT wait for or expect image data in the result.",
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
        "description": "Turn the monitor/screen off (blank the display). Use when the user says 'turn off the screen', 'blank the display', or similar.",
    },
    "monitor_on": {
        "method": "POST",
        "path": "/display/monitor/on",
        "description": "Turn the monitor/screen back on. Use when the user says 'turn on the screen', 'wake the display', or similar.",
    },
    "get_monitor_state": {
        "method": "GET",
        "path": "/display/monitor/state",
        "description": "Check whether the monitor is currently on or off. Use before toggling monitor state if unsure of the current state.",
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
        "description": "Lock the screen via the display manager (fast path, no fallbacks). Prefer lock_screen_security unless you specifically need the display-manager lock.",
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
        "description": (
            "Download a file from the local filesystem and send it to the user interface. "
            "Images are shown in the UI (not to the AI model) — you only get a success confirmation with path/size. "
            "Files larger than the configured limit are rejected with size details; do not retry the same path. "
            "Use for transferring a file the user asked to see or receive, not for reading file contents yourself."
        ),
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
        "description": "Search files and directories by name under allowed directories. Prefer path under the user home (e.g. /home/<user>). If path is / or omitted, search is automatically limited to configured allowed_base_dirs.",
        "input": {"query": "string", "path": "string?"},
    },
    "get_disk_usage": {
        "method": "GET",
        "path": "/fs/disk-usage",
        "description": "Disk space usage: how much free and used space each mounted partition has. Use when the user asks how much space is left or available. Do NOT use for partition layout or filesystem type — use get_system_disk for that.",
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
        "description": "Full list of all running processes with PIDs. Use when the user wants to find a specific process by name or get a PID to kill. Do NOT use to see what is consuming the most resources — use get_top_processes for that.",
    },
    "kill_process": {
        "method": "DELETE",
        "path": "/processes/{pid}",
        "description": "Kill a process by PID.",
        "input": {"pid": "integer"},
    },
    "kill_process_by_name": {
        "method": "DELETE",
        "path": "/processes/name/{name}",
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
    # ── Process control (extended) ────────────────────────────────────────────
    "launch_process": {
        "method": "POST",
        "path": "/processes/launch",
        "description": "Launch a raw shell command or system binary with arguments (e.g. 'bash', 'python3', 'ffmpeg'). Use for scripts and CLI tools. Do NOT use for named desktop apps — use open_application for those.",
        "input": {"command": "string", "args": "array of strings"},
    },
    "open_application": {
        "method": "POST",
        "path": "/processes/app/open",
        "description": "Open a user-facing application by its common name (e.g. 'firefox', 'gedit', 'vlc'). Use for everyday app launches. Do NOT use for raw shell commands or system binaries — use launch_process for those.",
        "input": {"name": "string", "args": "array of strings"},
    },
    "close_application": {
        "method": "POST",
        "path": "/processes/app/close",
        "description": "Close an application by process name.",
        "input": {"name": "string"},
    },
    "active_window": {
        "method": "GET",
        "path": "/processes/active-window",
        "description": "Get the currently focused window title and app path.",
    },
    "minimize_window": {
        "method": "POST",
        "path": "/processes/window/minimize",
        "description": "Minimize a window by window ID.",
        "input": {"window_id": "string"},
    },
    "close_window": {
        "method": "POST",
        "path": "/processes/window/close",
        "description": "Close a window by window ID.",
        "input": {"window_id": "string"},
    },
    # ── Power (extended) ──────────────────────────────────────────────────────
    "schedule_shutdown": {
        "method": "POST",
        "path": "/power/schedule-shutdown",
        "description": "Schedule a shutdown at a specific ISO datetime.",
        "input": {"at": "ISO datetime"},
    },
    "cancel_shutdown": {
        "method": "POST",
        "path": "/power/cancel-shutdown",
        "description": "Cancel a pending scheduled shutdown.",
    },
    "get_power_profile": {
        "method": "GET",
        "path": "/power/profile",
        "description": "Get the current power profile (performance, balanced, power-saver).",
    },
    "set_power_profile": {
        "method": "POST",
        "path": "/power/profile",
        "description": "Set the power profile.",
        "input": {"profile": "performance|balanced|power-saver"},
    },
    # ── Security ──────────────────────────────────────────────────────────────
    "lock_screen_security": {
        "method": "POST",
        "path": "/security/lock",
        "description": "Lock the screen with multiple fallbacks (most reliable). Use this when the user says 'lock', 'lock the screen', or 'lock my computer'. Prefer this over lock_screen_display.",
    },
    "logout_user": {
        "method": "POST",
        "path": "/security/logout",
        "description": "Log out the current user session.",
    },
    "disable_webcam": {
        "method": "POST",
        "path": "/security/webcam/disable",
        "description": "Disable the webcam by unloading the kernel module.",
    },
    "enable_webcam": {
        "method": "POST",
        "path": "/security/webcam/enable",
        "description": "Enable the webcam by loading the kernel module.",
    },
    "webcam_snapshot": {
        "method": "POST",
        "path": "/security/webcam/snapshot",
        "description": "Capture a webcam image and return it as base64 PNG.",
    },
    "disable_mic": {
        "method": "POST",
        "path": "/security/mic/disable",
        "description": "Mute the default microphone source.",
    },
    "enable_mic": {
        "method": "POST",
        "path": "/security/mic/enable",
        "description": "Unmute the default microphone source.",
    },
    "login_history": {
        "method": "GET",
        "path": "/security/login-history",
        "description": "Get recent login events from system auth logs.",
    },
    "ssh_sessions": {
        "method": "GET",
        "path": "/security/ssh-sessions",
        "description": "List active SSH sessions.",
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
        "description": "Clear all desktop notifications.",
    },
    "read_notifications": {
        "method": "GET",
        "path": "/notifications/read",
        "description": "Read only the notifications that were sent by this agent in the current session. Do NOT use for system-wide notification history — use list_notifications for that.",
    },
    "list_notifications": {
        "method": "GET",
        "path": "/notifications/list",
        "description": "List all desktop notification history system-wide (all apps). Use when the user asks to see recent notifications or missed alerts.",
    },
    # ── Maintenance ───────────────────────────────────────────────────────────
    "clear_cache": {
        "method": "POST",
        "path": "/maintenance/clear-cache",
        "description": "Clear /tmp and user cache directories.",
    },
    "get_logs": {
        "method": "GET",
        "path": "/maintenance/logs",
        "description": "Get the last N lines of a systemd service log.",
        "input": {"service": "string", "lines": "integer 1-1000"},
    },
    "check_updates": {
        "method": "GET",
        "path": "/maintenance/updates",
        "description": "Check for available system updates.",
    },
    "run_update": {
        "method": "POST",
        "path": "/maintenance/update",
        "description": "Run a full system update (requires confirmation).",
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
    # ── Network (extended) ────────────────────────────────────────────────────
    "speed_test": {
        "method": "GET",
        "path": "/network/speed-test",
        "description": "Run a network speed test (download, upload, ping).",
    },
    # ── Monitoring (extended) ─────────────────────────────────────────────────
    "monitor_battery_health": {
        "method": "GET",
        "path": "/monitor/battery-health",
        "description": "Get detailed battery health information (cycle count, capacity, health percent).",
    },
    "get_uptime": {
        "method": "GET",
        "path": "/monitor/uptime",
        "description": "Get system uptime: how long the laptop has been running since last boot, returned as seconds, minutes, hours, days, and a human-readable formatted string.",
    },
    # ── Filesystem (extended) ─────────────────────────────────────────────────
    "get_system_config": {
        "method": "GET",
        "path": "/fs/config",
        "description": "Get system configuration (home directory, username).",
    },
    "get_directory_tree": {
        "method": "GET",
        "path": "/fs/tree",
        "description": "Get directory tree structure for folder navigation.",
        "input": {"path": "string", "max_depth": "integer 1-3"},
    },
    # ── Audio (extended) ──────────────────────────────────────────────────────
    "beep_audio": {
        "method": "POST",
        "path": "/audio/beep",
        "description": "Play a simple notification beep sound.",
    },
    # ── Alerts / Monitoring (new) ────────────────────────────────────────────
    "check_alert_status": {
        "method": "GET",
        "path": "/alerts/status",
        "description": "Check the monitoring system status: whether spike alerts and daily summaries are scheduled, alerts today, and recipient email from .env. No email input needed — reads RECIPIENT_EMAIL from .env.",
    },
    "send_test_spike_alert": {
        "method": "POST",
        "path": "/alerts/spike/check",
        "description": "Manually check CPU/memory and send an alert email if thresholds are exceeded. Email goes to RECIPIENT_EMAIL from .env (no prompt). Optional: cpu_threshold (default 80%), memory_threshold (default 85%).",
        "input": {"cpu_threshold": "float?", "memory_threshold": "float?"},
    },
    "send_daily_summary_now": {
        "method": "POST",
        "path": "/alerts/summary/send",
        "description": "Send the daily system summary email right now. Includes CPU, memory, vnstat network stats, top processes. Goes to RECIPIENT_EMAIL from .env — no email prompt.",
    },
    "send_test_email": {
        "method": "GET",
        "path": "/alerts/test",
        "description": "Send a test spike alert email to RECIPIENT_EMAIL (from .env) to verify Resend is working. Always sends regardless of CPU/memory. No email input needed.",
    },
    "check_vnstat_status": {
        "method": "GET",
        "path": "/network/vnstat",
        "description": "Check if vnstat is installed, its version, and which network interfaces it's monitoring.",
    },
    "get_vnstat_data": {
        "method": "GET",
        "path": "/network/usage",
        "description": "Get network usage from vnstat for a specific period. period: 'day' (today — default), 'month' (this month), 'hour' (current hour). Use when the user asks about their data usage or bandwidth.",
        "input": {"period": "string?"},
    },
    "get_system_stats": {
        "method": "GET",
        "path": "/alerts/stats",
        "description": "Get current system stats on demand: CPU usage, memory, vnstat network (today + month), top processes, uptime. Use when the user asks 'how's my system', 'give me stats', 'show system status'.",
    },
    # ── Spotify ────────────────────────────────────────────────────────────────
    "search_and_play": {
        "method": "POST",
        "path": "/spotify/search-and-play",
        "description": "Search Spotify for a song and immediately play it. Use when the user wants to hear a specific song.",
        "input": {"query": "string", "device_id": "string?"},
    },
    "spotify_devices": {
        "method": "GET",
        "path": "/spotify/devices",
        "description": "Get list of available Spotify playback devices (speakers, computers, phones). Use when the user asks what devices are available for playback.",
    },
    "spotify_auth": {
        "method": "GET",
        "path": "/spotify/auth",
        "description": "Start Spotify account linking. Returns an auth URL the user must open in a browser to sign in and approve access. After approving Spotify, the user is redirected to the configured callback URL; from there finish linking by calling spotify_callback with the authorization code.",
    },
    "spotify_callback": {
        "method": "GET",
        "path": "/spotify/callback",
        "description": "Complete Spotify account linking after the user approved access in the browser. Provide the authorization code from the callback redirect.",
        "input": {"code": "string"},
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

# Human-readable display names sent to the client instead of raw tool identifiers
TOOL_DISPLAY_NAMES: dict[str, str] = {
    "get_system_info": "Gathering full system snapshot",
    "get_system_cpu": "Reading CPU details",
    "get_system_ram": "Reading memory usage",
    "get_system_gpu": "Detecting GPU devices",
    "get_system_disk": "Checking disk partitions",
    "get_system_os": "Reading OS information",
    "get_system_usb": "Listing USB devices",
    "get_system_monitors": "Reading monitor info",
    "get_system_bios": "Reading BIOS information",
    "get_device_info": "Identifying your device",
    "get_network_ip": "Looking up IP addresses",
    "get_network_location": "Looking up network location",
    "get_wifi_status": "Checking WiFi status",
    "list_wifi_networks": "Scanning WiFi networks",
    "connect_wifi": "Connecting to WiFi",
    "disconnect_wifi": "Disconnecting from WiFi",
    "toggle_wifi": "Toggling WiFi",
    "list_bluetooth_devices": "Scanning Bluetooth devices",
    "pair_bluetooth_device": "Pairing Bluetooth device",
    "unpair_bluetooth_device": "Unpairing Bluetooth device",
    "toggle_bluetooth": "Toggling Bluetooth",
    "ping_host": "Pinging host",
    "get_snapshot": "Taking live metrics snapshot",
    "monitor_cpu": "Reading CPU usage",
    "monitor_ram": "Reading memory usage",
    "monitor_gpu": "Reading GPU usage",
    "monitor_disk_io": "Reading disk I/O",
    "monitor_network_io": "Reading network I/O",
    "monitor_temperatures": "Reading temperature sensors",
    "monitor_fans": "Reading fan speeds",
    "get_battery": "Reading battery status",
    "get_top_processes": "Reading top processes",
    "get_volume": "Reading audio volume",
    "set_volume": "Setting audio volume",
    "volume_up": "Increasing volume",
    "volume_down": "Decreasing volume",
    "mute_audio": "Toggling mute",
    "audio_devices": "Listing audio devices",
    "set_output_device": "Switching audio output",
    "get_currently_playing_song": "Checking what's playing",
    "toggle_play_pause": "Toggling playback",
    "next_track": "Skipping to next track",
    "previous_track": "Going to previous track",
    "seek_media": "Seeking media",
    "read_clipboard": "Reading clipboard",
    "write_clipboard": "Writing to clipboard",
    "clear_clipboard": "Clearing clipboard",
    "display_screenshot": "Taking a screenshot",
    "monitor_off": "Turning monitor off",
    "monitor_on": "Turning monitor on",
    "get_monitor_state": "Checking monitor state",
    "get_display_brightness": "Reading brightness",
    "set_display_brightness": "Setting brightness",
    "get_resolution": "Reading resolution",
    "set_resolution": "Setting resolution",
    "rotate_display": "Rotating display",
    "lock_screen_display": "Locking screen",
    "set_night_light": "Adjusting night light",
    "list_files": "Listing files",
    "download_file": "Downloading file",
    "upload_file": "Uploading file",
    "delete_path": "Deleting file or directory",
    "make_directory": "Creating directory",
    "rename_path": "Renaming path",
    "search_files": "Searching files",
    "get_disk_usage": "Checking disk usage",
    "zip_paths": "Creating archive",
    "unzip_path": "Extracting archive",
    "open_path": "Opening file or directory",
    "move_mouse": "Moving mouse",
    "click_mouse": "Clicking mouse",
    "double_click_mouse": "Double-clicking mouse",
    "scroll_mouse": "Scrolling",
    "type_keyboard": "Typing text",
    "press_keyboard_keys": "Pressing keys",
    "list_processes": "Listing processes",
    "kill_process": "Killing process",
    "kill_process_by_name": "Killing processes by name",
    "power_shutdown": "Shutting down",
    "power_restart": "Restarting",
    "power_sleep": "Putting to sleep",
    "power_hibernate": "Hibernating",
    "schedule_job": "Scheduling task",
    "list_jobs": "Listing scheduled tasks",
    "cancel_job": "Cancelling scheduled task",
    "run_job_now": "Running scheduled task now",
    "launch_process": "Launching process",
    "open_application": "Opening application",
    "close_application": "Closing application",
    "active_window": "Reading active window",
    "minimize_window": "Minimizing window",
    "close_window": "Closing window",
    "schedule_shutdown": "Scheduling shutdown",
    "cancel_shutdown": "Cancelling shutdown",
    "get_power_profile": "Reading power profile",
    "set_power_profile": "Setting power profile",
    "lock_screen_security": "Locking screen",
    "logout_user": "Logging out",
    "disable_webcam": "Disabling webcam",
    "enable_webcam": "Enabling webcam",
    "webcam_snapshot": "Capturing webcam photo",
    "disable_mic": "Disabling microphone",
    "enable_mic": "Enabling microphone",
    "login_history": "Reading login history",
    "ssh_sessions": "Reading SSH sessions",
    "send_notification": "Sending notification",
    "clear_notifications": "Clearing notifications",
    "read_notifications": "Reading notifications",
    "list_notifications": "Listing notifications",
    "clear_cache": "Clearing cache",
    "get_logs": "Reading logs",
    "check_updates": "Checking for updates",
    "run_update": "Running system update",
    "sync_time": "Syncing system clock",
    "list_services": "Listing services",
    "restart_service": "Restarting service",
    "stop_service": "Stopping service",
    "start_service": "Starting service",
    "speed_test": "Running speed test",
    "monitor_battery_health": "Checking battery health",
    "get_uptime": "Checking system uptime",
    "get_system_config": "Reading system config",
    "get_directory_tree": "Reading directory structure",
    "beep_audio": "Playing beep",
    "check_alert_status": "Checking alert monitoring status",
    "send_test_spike_alert": "Checking CPU/memory and sending alerts",
    "send_daily_summary_now": "Sending daily summary report",
    "send_test_email": "Sending test email",
    "check_vnstat_status": "Checking vnstat status",
    "get_vnstat_data": "Getting network usage data",
    "get_system_stats": "Fetching system stats",
    "search_and_play": "Playing song on Spotify",
    "spotify_devices": "Listing Spotify playback devices",
    "spotify_auth": "Starting Spotify sign-in",
    "spotify_callback": "Finishing Spotify sign-in",
}


# Map common model hallucinations / alternate names to canonical tool names
TOOL_ALIASES: dict[str, str] = {
    "set_power_mode": "set_power_profile",
    "set_power": "set_power_profile",
    "change_power_profile": "set_power_profile",
    "change_power_mode": "set_power_profile",
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
6. BIAS TO ACTION: If intent implies an action, execute it. NEVER ask "would you like me to..." for safe actions.
7. TOOL-FIRST EXECUTION: If a user request requires a tool call, you MUST emit the tool call in the SAME response before any conversational reply. Never defer tool execution to a later turn.

TOOL-FIRST VALIDATION:
- Before responding, ask: "Does this request require a tool call?"
- If YES: Include the tool call FIRST in your JSON array, then optionally add a conversational_reply.
- If NO: Return only a conversational_reply with tool="none".

VALID RESPONSE PATTERNS:
- Tool call ONLY (action without text): [{{"tool":"mute_audio","tool_input":{{"muted":true}}}}]
- Tool call + text: [{{"tool":"mute_audio","tool_input":{{"muted":true}}}},{{"tool":"none","tool_input":{{}},"conversational_reply":"Muted. 🔇"}}]
- Text ONLY (no action needed): [{{"tool":"none","tool_input":{{}},"conversational_reply":"Hello! How can I help?"}}]

TOOL DEPENDENCIES:
- Independent tool calls run in parallel. When one action must finish before another, add `"depends_on":[N]` to the dependent call, where N is the zero-based position of its prerequisite in this JSON array.
- Example: `[{{"tool":"open_application","tool_input":{{"name":"spotify"}}}},{{"tool":"toggle_play_pause","tool_input":{{}},"depends_on":[0]}},{{"tool":"search_and_play","tool_input":{{"query":"Wicked by Future"}},"depends_on":[1]}}]`
- Only add dependencies for real prerequisites; do not serialize unrelated operations.
- For "open Spotify and play <song>", emit open Spotify → toggle playback → search_and_play in that order with dependencies. The backend will enforce this workflow too.

CONDITIONAL REQUESTS:
- When the request says "if", "if yes/no", or "otherwise", this is a two-stage workflow.
- In the FIRST stage, emit ONLY read-only inspection tools needed to evaluate the conditions. Do NOT guess a branch or emit actions yet.
- Vela will send the inspection results in one follow-up planning request. In that follow-up, emit only the actions for the branch whose condition is true.
- Example: for "if music is playing mute it, otherwise set volume to 60", first emit only get_currently_playing_song.

Intent → Tool mappings (use these as a starting point — always reason about what the situation fully requires, do not limit yourself to the exact tools shown):
- "leaving"/"going out"/"stepping away"/"brb" → lock_screen_security + mute_audio(muted:true) + monitor_off
- "nap"/"sleeping"/"going to sleep"/"bed" → set_display_brightness(0) + mute_audio(muted:true) + monitor_off + power_sleep
- "I'm back"/"back now"/"wake up" → monitor_on + mute_audio(muted:false)
- "mute"/"silence"/"quiet" → mute_audio(muted:true)
- "unmute"/"sound on" → mute_audio(muted:false)
- "volume up/down a bit" → step of 10
- "turn off screen/display/monitor" → monitor_off
- "lock"/"lock screen" → lock_screen_security
- "screenshot" → display_screenshot
- "what's playing"/"now playing" → get_currently_playing_song
- "battery"/"how much battery" → get_battery
- "battery health"/"battery condition"/"is my battery healthy"/"battery wear" → monitor_battery_health
- "how's my pc"/"system status" → get_snapshot
- "bluetooth on/off" → toggle_bluetooth(enabled:true/false)
- "kill process <PID>" → kill_process(pid:<PID as integer>)
- "kill <process name>"/"kill all <name>" → kill_process_by_name(name:<process name>)

IMPORTANT: The mappings above are common examples only. Always emit ALL tools a situation logically requires. A user saying "I'm heading out for the night" might need lock + mute + monitor off + even sleep depending on context. Reason about completeness, do not cap tool calls to match the number shown in any example.

Valid response formats — these show structure only, not a limit on array length:
- Single tool: [{{"tool":"get_battery","tool_input":{{}}}}]
- Two tools: [{{"tool":"mute_audio","tool_input":{{"muted":true}}}},{{"tool":"lock_screen_security","tool_input":{{}}}}]
- Many tools: the array may contain as many tool objects as the situation requires
- Conversation only: [{{"tool":"none","tool_input":{{}},"conversational_reply":"Your reply here"}}]

Available tools:
{_TOOL_LIST}

REMEMBER: Output ONLY the JSON array. Nothing else. When in doubt about intent, act — don't ask."""