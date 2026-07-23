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
        "description": "Capture the current screen with flameshot to ~/Pictures and return it to the client as base64 image data (compressed for relay delivery when large). The AI model only receives a success confirmation — the image is delivered to the user interface separately.",
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
        "path": "/processes",
        "description": "Full list of all running processes with PIDs. Use when the user wants to find a specific process by name or get a PID to kill. Do NOT use to see what is consuming the most resources — use get_top_processes for that.",
    },
    "is_process_running": {
        "method": "GET",
        "path": "/processes/running/{name}",
        "description": "Check whether a process or app is currently running by name. Use FIRST when asked if an application/process is open — do NOT launch it just to check.",
        "input": {"name": "string"},
    },
    "list_installed_applications": {
        "method": "GET",
        "path": "/processes/apps",
        "description": "List installed desktop applications from this machine (.desktop entries): display name, desktop id, exec binary. Use when the user asks what apps are installed, what browser/IDE they have, or before opening an ambiguous app name.",
        "input": {"filter": "string?"},
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
    "open_application": {
        "method": "POST",
        "path": "/processes/app/open",
        "description": "Open a desktop/GUI application. Accepts friendly names ('Chrome', 'firefox'), .desktop ids ('google-chrome.desktop'), or exec binaries — resolved against installed .desktop entries on this PC. Use list_installed_applications when unsure of the exact name.",
        "input": {"name": "string", "args": "array of strings"},
    },
    "close_application": {
        "method": "POST",
        "path": "/processes/app/close",
        "description": "Close a desktop/GUI application. Accepts the same friendly names and .desktop resolution as open_application (e.g. 'Chrome', 'firefox'). Matches running processes by exec binary and process name.",
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
        "query_input": True,
    },
    "sync_time": {
        "method": "POST",
        "path": "/maintenance/sync-time",
        "description": "Sync the system clock via NTP.",
    },
    "list_services": {
        "method": "GET",
        "path": "/maintenance/services",
        "description": "List systemd services and their status. Use filter to narrow results and scope=system|user|all for system vs user units (Vela runs as user services). Do NOT use to answer whether one specific service is running — use get_service_status instead.",
        "input": {"filter": "string?", "scope": "system|user|all"},
    },
    "get_service_status": {
        "method": "GET",
        "path": "/maintenance/service/status",
        "description": "Check whether a specific systemd service is running, failed, or stopped. Use FIRST when the user asks if a service is up/running/active. Do NOT start or restart the service to answer a status question.",
        "input": {"name": "string", "scope": "system|user|all"},
    },
    "list_failed_services": {
        "method": "GET",
        "path": "/maintenance/services/failed",
        "description": "List failed systemd units from the current boot.",
        "input": {"scope": "system|user|all"},
    },
    "list_timers": {
        "method": "GET",
        "path": "/maintenance/timers",
        "description": "List systemd timers and when they next run.",
        "input": {"filter": "string?", "scope": "system|user|all"},
    },
    "check_package_installed": {
        "method": "GET",
        "path": "/maintenance/package-installed",
        "description": "Check whether a package is installed (apt/dnf/pacman).",
        "input": {"name": "string"},
    },
    "get_boot_errors": {
        "method": "GET",
        "path": "/maintenance/boot-errors",
        "description": "Recent error-level journal entries from the current boot.",
        "input": {"lines": "integer 1-500"},
    },
    "restart_service": {
        "method": "POST",
        "path": "/maintenance/service/restart",
        "description": "Restart a systemd service. Use only when the user asks to restart/fix it — not to check status.",
        "input": {"name": "string", "scope": "system|user|all"},
        "query_input": True,
    },
    "stop_service": {
        "method": "POST",
        "path": "/maintenance/service/stop",
        "description": "Stop a systemd service.",
        "input": {"name": "string", "scope": "system|user|all"},
        "query_input": True,
    },
    "start_service": {
        "method": "POST",
        "path": "/maintenance/service/start",
        "description": "Start a systemd service. Use get_service_status first when the user asks if it is running; only start when they ask to start it or it is down and they want it fixed.",
        "input": {"name": "string", "scope": "system|user|all"},
        "query_input": True,
    },
    # ── Docker ────────────────────────────────────────────────────────────────
    "get_docker_info": {
        "method": "GET",
        "path": "/docker/info",
        "description": "Check whether Docker is installed and the daemon is running.",
    },
    "list_docker_containers": {
        "method": "GET",
        "path": "/docker/containers",
        "description": "List Docker containers. Use when the user asks what containers are running or to find a container by name/image.",
        "input": {"all": "boolean", "filter": "string?"},
    },
    "get_container_status": {
        "method": "GET",
        "path": "/docker/containers/{name_or_id}",
        "description": "Detailed status for one Docker container. Use FIRST when asked if a container is running.",
        "input": {"name_or_id": "string"},
    },
    "get_container_logs": {
        "method": "GET",
        "path": "/docker/containers/{name_or_id}/logs",
        "description": "Recent logs from a Docker container.",
        "input": {"name_or_id": "string", "lines": "integer 1-1000"},
    },
    "start_container": {
        "method": "POST",
        "path": "/docker/containers/{name_or_id}/start",
        "description": "Start a Docker container. Check status first unless the user explicitly asked to start it.",
        "input": {"name_or_id": "string"},
    },
    "stop_container": {
        "method": "POST",
        "path": "/docker/containers/{name_or_id}/stop",
        "description": "Stop a Docker container.",
        "input": {"name_or_id": "string"},
    },
    "restart_container": {
        "method": "POST",
        "path": "/docker/containers/{name_or_id}/restart",
        "description": "Restart a Docker container.",
        "input": {"name_or_id": "string"},
    },
    "compose_status": {
        "method": "GET",
        "path": "/docker/compose",
        "description": "List services from a Docker Compose project.",
        "input": {"project_directory": "string?", "project": "string?"},
    },
    # ── Network (extended) ────────────────────────────────────────────────────
    "speed_test": {
        "method": "GET",
        "path": "/network/speed-test",
        "description": "Run a network speed test (download, upload, ping).",
    },
    "check_port": {
        "method": "GET",
        "path": "/network/port/{port}",
        "description": "Find what process is listening on a TCP port on this machine. Use when the user asks what service/app uses a port, what's on port X, or if a port is open (e.g. 8765 for the local Vela API). Returns PID, process name, and command line.",
        "input": {"port": "integer"},
    },
    "health_check": {
        "method": "GET",
        "path": "/network/health-check",
        "description": "Probe an HTTP(S) URL and report whether it responds.",
        "input": {"url": "string"},
    },
    "get_firewall_status": {
        "method": "GET",
        "path": "/network/firewall",
        "description": "Get ufw firewall status when installed.",
    },
    "get_vpn_status": {
        "method": "GET",
        "path": "/network/vpn",
        "description": "Check whether a VPN interface or NetworkManager VPN connection is active.",
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
    # ── Push ──────────────────────────────────────────────────────────────────
    "send_push_notification": {
        "method": "POST",
        "path": "/push/send",
        "description": "Send a push notification to the user's registered mobile devices.",
        "input": {"title": "string", "body": "string", "data": "object?"},
    },
    # ── Spotify ────────────────────────────────────────────────────────────────
    "search_and_play": {
        "method": "POST",
        "path": "/spotify/search-and-play",
        "description": "Search Spotify for a song and immediately play it. If no active device is available, Vela opens the local Spotify app and registers this PC as a playback device before retrying. Use when the user wants to hear a specific song.",
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
        "description": "Start Spotify account linking. Returns an auth URL the user must open in a browser to sign in and approve access. After approving, Spotify redirects to the configured callback URL and Vela finishes linking automatically — the browser should show a success or failure page.",
    },
    "spotify_callback": {
        "method": "GET",
        "path": "/spotify/callback",
        "description": "Legacy/manual completion of Spotify linking with an authorization code. Prefer the automatic browser redirect to /spotify/callback; only use this if the redirect could not finish linking.",
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
    "get_device_info": "Identifying your device/laptop/computer",
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
    "list_installed_applications": "Listing installed applications",
    "kill_process": "Killing process",
    "kill_process_by_name": "Killing processes by name",
    "schedule_job": "Scheduling task",
    "list_jobs": "Listing scheduled tasks",
    "cancel_job": "Cancelling scheduled task",
    "run_job_now": "Running scheduled task now",
    "open_application": "Opening application",
    "close_application": "Closing application",
    "active_window": "Reading active window",
    "minimize_window": "Minimizing window",
    "close_window": "Closing window",
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
    "get_service_status": "Checking service status",
    "list_failed_services": "Listing failed services",
    "list_timers": "Listing systemd timers",
    "check_package_installed": "Checking package installation",
    "get_boot_errors": "Reading boot errors",
    "restart_service": "Restarting service",
    "stop_service": "Stopping service",
    "start_service": "Starting service",
    "get_docker_info": "Checking Docker status",
    "list_docker_containers": "Listing Docker containers",
    "get_container_status": "Checking container status",
    "get_container_logs": "Reading container logs",
    "start_container": "Starting container",
    "stop_container": "Stopping container",
    "restart_container": "Restarting container",
    "compose_status": "Checking compose services",
    "speed_test": "Running speed test",
    "check_port": "Checking port",
    "health_check": "Probing endpoint",
    "get_firewall_status": "Checking firewall",
    "get_vpn_status": "Checking VPN status",
    "is_process_running": "Checking if process is running",
    "send_push_notification": "Sending push notification",
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

SYSTEM_TOOL_PROMPT = f"""You are Vela's tool picker. Output ONLY a JSON array — no markdown wrapper, no prose outside the array.

JSON RULES (non-negotiable):
1. Response starts with '[' and ends with ']'.
2. Every message gets a JSON array — greetings, thanks, chit-chat included.
3. Plain text outside the array breaks the app. Put personality in `conversational_reply`, not outside the array.
4. If tools are needed: emit tool object(s) FIRST, then optional {{"tool":"none",...,"conversational_reply":"..."}}.
5. Safe actions: do them. Don't ask "would you like me to…".
6. `conversational_reply` should sound like Vela (human, blunt, not corporate) — but only when you're not skipping straight to tool execution.
7. **Confirmation/PIN is app-handled.** For risky tools (delete, kill, stop/start service or container, etc.), emit the tool call directly. The server pauses execution and shows its own gate UI — never ask for PIN, yes/no, or approval in `conversational_reply`, and never use tool=none to gate an action you could call with a tool.

WHEN TO USE TOOLS:
- Read the user's actual intent and pick the best tool(s) from the list below.
- Combine tools freely. One user message can need several calls.
- Do NOT treat phrase-matching as your job. The hints below are examples of what people often mean — not a lookup table. If "heading out" needs lock + mute + screen off + sleep, emit all of them even if the hint only shows three.
- If no tool applies and it's in Vela's scope but unsupported, use tool=none and say there's no tool.
- If it's pure conversation (thanks, hi, joke in scope), tool=none with a short conversational_reply.
- **Nicknames / "call me X" / "call yourself X":** no tools. tool=none only. Refuse in conversational_reply — disgusted/blunt ("Ew.", "Wtf.", "That's weird.", "No."). Never use their requested name.
- **Inspection / status / diagnostics:** read-only tools only. No arbitrary shell or process launch for checks.

TOOL DEPENDENCIES:
- Independent calls can run in parallel.
- When B must wait for A, add `"depends_on":[N]` (0-based index of prerequisite).
- Spotify play: search_and_play alone is enough — the server auto-opens Spotify and activates this PC first. Optional explicit chain: open_application(spotify) → toggle_play_pause → search_and_play.

CONDITIONAL ("if / otherwise"):
- First pass: read-only inspection tools only. Don't guess the branch.
- Follow-up pass (after results): actions for the branch that matched.

COMMON PATTERNS (hints only — adapt, extend, ignore if wrong):
- leaving / brb → often lock + mute + monitor off (never shutdown/restart/sleep — no tools for those)
- nap / bed → dim/off screen, mute; do NOT shutdown/sleep the machine from chat
- back / wake up → monitor on, unmute
- mute / quiet → mute_audio(true); unmute → mute_audio(false)
- volume nudge → step ~10
- screenshot → display_screenshot
- now playing → get_currently_playing_song
- battery → get_battery; battery health → monitor_battery_health
- system check → get_snapshot
- bluetooth on/off → toggle_bluetooth
- kill process by pid/name → kill_process / kill_process_by_name (app PIN gate when configured)
- stop/kill docker container → stop_container (app confirmation gate — not kill_process)
- is service running? → get_service_status (scope=all for Vela user units); answer before start/restart
- are containers running? → list_docker_containers or get_container_status; answer before start/restart
- is app/process open? → is_process_running; do NOT open_application just to check
- open app / launch chrome / start firefox → open_application with tool_input.name (e.g. {{"name":"chrome"}})
- close app / quit chrome → close_application with tool_input.name (e.g. {{"name":"spotify"}})
- port listening / what uses port X / what's on 8765? → check_port ONLY
- HTTP endpoint up? → health_check (e.g. http://127.0.0.1:8765/health for Vela API)
- docker/compose status → get_docker_info, list_docker_containers, compose_status

RESPONSE SHAPES:
- Action only: [{{"tool":"mute_audio","tool_input":{{"muted":true}}}}]
- Action + vibe: [{{"tool":"mute_audio","tool_input":{{"muted":true}}}},{{"tool":"none","tool_input":{{}},"conversational_reply":"Muted. You're welcome."}}]
- Chat only: [{{"tool":"none","tool_input":{{}},"conversational_reply":"Yeah?"}}]

Available tools:
{_TOOL_LIST}

Output ONLY the JSON array. When unsure between asking and acting on a safe read/action, act."""