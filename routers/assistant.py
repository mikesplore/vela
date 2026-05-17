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

TOOL_DEFINITIONS = {
    "get_system_info": {
        "method": "GET",
        "path": "/system/info",
        "description": "Return the full system snapshot, including CPU, RAM, GPU, disk, OS, USB, monitors, and BIOS details.",
        "response": "{cpu: {...}, ram: {...}, gpu: [...], disk: [...], os: {...}, usb: [...], monitors: [...], bios: {...}}",
    },
    "get_system_cpu": {
        "method": "GET",
        "path": "/system/cpu",
        "description": "Return CPU model, core counts, base frequency, and architecture.",
        "response": "{model: \"Intel Core i7-1165G7\", physical_cores: 4, logical_cores: 8, base_freq_mhz: 2900.0, architecture: \"x86_64\"}",
    },
    "get_system_ram": {
        "method": "GET",
        "path": "/system/ram",
        "description": "Return RAM and swap usage statistics.",
        "response": "{total: 17179869184, available: 8320000000, used: 8340000000, percent: 48.5, swap_total: 2147483648, swap_used: 0, swap_free: 2147483648, swap_percent: 0.0}",
    },
    "get_system_gpu": {
        "method": "GET",
        "path": "/system/gpu",
        "description": "Return detected GPU devices.",
        "response": "[{name: \"Intel UHD Graphics\", vram_total_mb: null, driver: null, vendor: \"Intel\"}]",
    },
    "get_system_disk": {
        "method": "GET",
        "path": "/system/disk",
        "description": "Return disk partition usage information.",
        "response": "[{mountpoint: \"/\", total: 100000000000, used: 45000000000, free: 45000000000, percent: 45.0, filesystem: \"ext4\"}]",
    },
    "get_system_os": {
        "method": "GET",
        "path": "/system/os",
        "description": "Return operating system, kernel, hostname, user, and uptime.",
        "response": "{os_name: \"Linux\", os_version: \"5.15.0\", kernel: \"5.15.0-79-generic\", hostname: \"mylaptop\", user: \"mike\", uptime_seconds: 3600}",
    },
    "get_system_usb": {
        "method": "GET",
        "path": "/system/usb",
        "description": "Return connected USB devices.",
        "response": "[{bus: \"001\", device: \"002\", id: \"046d:c534\", description: \"Logitech USB Receiver\"}]",
    },
    "get_system_monitors": {
        "method": "GET",
        "path": "/system/monitors",
        "description": "Return connected monitor details.",
        "response": "[{name: \"HDMI-1\", resolution: \"1920x1080\", refresh_rate: 60.0}]",
    },
    "get_system_bios": {
        "method": "GET",
        "path": "/system/bios",
        "description": "Return BIOS and motherboard vendor, version, release date, and product name.",
        "response": "{vendor: \"Dell Inc.\", version: \"1.2.3\", release_date: \"2024-01-01\", motherboard: \"XPS 15 9520\"}",
    },
    "get_network_ip": {
        "method": "GET",
        "path": "/network/ip",
        "description": "Return local and public IP addresses for the machine.",
        "response": "{local_ip: \"192.168.1.10\", public_ip: \"1.2.3.4\"}",
    },
    "get_network_location": {
        "method": "GET",
        "path": "/network/location",
        "description": "Return the machine's public IP and geo-location, including city, region, country, timezone, ISP, and coordinates.",
        "response": "{local_ip: \"192.168.1.10\", public_ip: \"1.2.3.4\", location: {status: \"success\", country: \"United States\", region: \"California\", city: \"San Francisco\", zip: \"94107\", timezone: \"America/Los_Angeles\", isp: \"Example ISP\", org: \"Example Org\", lat: 37.78, lon: -122.39}}",
    },
    "list_bluetooth_devices": {
        "method": "GET",
        "path": "/network/bluetooth/devices",
        "description": "List paired and available Bluetooth devices.",
        "response": "[{address: \"AA:BB:CC:DD:EE:FF\", name: \"Test Device\"}]",
    },
    "toggle_bluetooth": {
        "method": "POST",
        "path": "/network/bluetooth/toggle",
        "description": "Enable or disable the Bluetooth radio.",
        "input": {"enabled": "boolean"},
        "response": "{local_ip: \"192.168.1.10\", public_ip: \"1.2.3.4\"}",
    },
    "get_battery": {
        "method": "GET",
        "path": "/monitor/battery",
        "description": "Return battery percent, plugged_in state and seconds remaining.",
        "response": "{percent: 87.0, plugged_in: false, secs_left: 14000}",
    },
    "get_snapshot": {
        "method": "GET",
        "path": "/monitor/snapshot",
        "description": "Return live metrics for CPU, RAM, GPU, disk IO, network IO, temperatures, fans, battery, and processes.",
        "response": "{cpu: {...}, ram: {...}, gpu: [...], disk_io: [...], network_io: [...], temperatures: [...], fans: [...], battery: {...}, processes: {...}}",
    },
    "get_top_processes": {
        "method": "GET",
        "path": "/monitor/processes",
        "description": "Return top processes by CPU and memory.",
        "response": "{top_by_cpu:[...], top_by_memory:[...]}"
    },
    "get_media_status": {
        "method": "GET",
        "path": "/media/now-playing",
        "description": "Return the current playback status, title, artist, album, and position.",
        "response": "{title: \"Test Song\", artist: \"Test Artist\", album: \"Test Album\", art_url: \"...\", status: \"Playing\", position_seconds: 42.0, length_seconds: 120.0}"
    },
    "toggle_play_pause": {
        "method": "POST",
        "path": "/media/play-pause",
        "description": "Toggle media playback on or off.",
        "response": "{success: true, message: \"playback toggled\"}"
    },
    "next_track": {
        "method": "POST",
        "path": "/media/next",
        "description": "Skip to the next media track.",
        "response": "{success: true, message: \"skipped to next track\"}"
    },
    "previous_track": {
        "method": "POST",
        "path": "/media/previous",
        "description": "Skip to the previous media track.",
        "response": "{success: true, message: \"skipped to previous track\"}"
    },
    "set_volume": {
        "method": "POST",
        "path": "/audio/volume",
        "description": "Set audio volume to a specific percentage.",
        "input": {"value": "integer 0-100"},
        "response": "{volume: 60, muted: false}"
    },
    "get_volume": {
        "method": "GET",
        "path": "/audio/volume",
        "description": "Read the current master volume and mute state.",
        "response": "{volume: 60, muted: false}"
    },
    "volume_up": {
        "method": "POST",
        "path": "/audio/volume/up",
        "description": "Increase the master volume by a step.",
        "input": {"step": "integer 1-20"},
        "response": "{volume: 65, muted: false}"
    },
    "volume_up_get": {
        "method": "GET",
        "path": "/audio/volume/up",
        "description": "Increase the master volume by a step via query parameter.",
        "input": {"step": "integer"},
        "response": "{volume: 65, muted: false}"
    },
    "volume_down": {
        "method": "POST",
        "path": "/audio/volume/down",
        "description": "Decrease the master volume by a step.",
        "input": {"step": "integer 1-20"},
        "response": "{volume: 55, muted: false}"
    },
    "volume_down_get": {
        "method": "GET",
        "path": "/audio/volume/down",
        "description": "Decrease the master volume by a step via query parameter.",
        "input": {"step": "integer"},
        "response": "{volume: 55, muted: false}"
    },
    "mute_audio": {
        "method": "POST",
        "path": "/audio/mute",
        "description": "Mute or unmute the master audio channel.",
        "input": {"muted": "boolean"},
        "response": "{volume: 60, muted: true}"
    },
    "mute_audio_get": {
        "method": "GET",
        "path": "/audio/mute",
        "description": "Mute or unmute the master audio channel via query parameter.",
        "input": {"muted": "boolean"},
        "response": "{volume: 60, muted: true}"
    },
    "audio_devices": {
        "method": "GET",
        "path": "/audio/devices",
        "description": "List available audio sinks and sources.",
        "response": "[{id: \"1\", name: \"Built-in Audio\", type: \"sink\"}]"
    },
    "audio_output_devices": {
        "method": "GET",
        "path": "/audio/output-devices",
        "description": "Alias for listing audio devices.",
        "response": "[{id: \"1\", name: \"Built-in Audio\", type: \"sink\"}]"
    },
    "set_output_device": {
        "method": "POST",
        "path": "/audio/output-device",
        "description": "Switch the default audio output device.",
        "input": {"device_id": "string"},
        "response": "{volume: 60, muted: false}"
    },
    "set_output_device_get": {
        "method": "GET",
        "path": "/audio/output-device",
        "description": "Switch the default audio output device via query parameter.",
        "input": {"device_id": "string"},
        "response": "{volume: 60, muted: false}"
    },
    "display_screenshot": {
        "method": "GET",
        "path": "/display/screenshot",
        "description": "Capture the current screen and return a PNG as base64.",
        "response": "{image_base64: \"...\"}"
    },
    "display_record": {
        "method": "POST",
        "path": "/display/record",
        "description": "Record a short screen clip and return MP4 as base64.",
        "input": {"duration_seconds": "integer 1-60"},
        "response": "{image_base64: \"...\"}"
    },
    "monitor_off": {
        "method": "POST",
        "path": "/display/monitor/off",
        "description": "Turn the monitor off.",
        "response": "{success: true, message: \"monitor off\"}"
    },
    "monitor_on": {
        "method": "POST",
        "path": "/display/monitor/on",
        "description": "Turn the monitor on.",
        "response": "{success: true, message: \"monitor on\"}"
    },
    "get_display_brightness": {
        "method": "GET",
        "path": "/display/brightness",
        "description": "Get the current screen brightness.",
        "response": "{brightness: 70.0}"
    },
    "set_display_brightness": {
        "method": "POST",
        "path": "/display/brightness",
        "description": "Set the screen brightness.",
        "input": {"value": "integer 0-100"},
        "response": "{success: true, message: \"brightness set to 70\"}"
    },
    "get_resolution": {
        "method": "GET",
        "path": "/display/resolution",
        "description": "Get the current display resolution and refresh rate.",
        "response": "{width: 1920, height: 1080, refresh: 60.0, output: \"HDMI-1\"}"
    },
    "set_resolution": {
        "method": "POST",
        "path": "/display/resolution",
        "description": "Set the display resolution and refresh rate.",
        "input": {"width": "integer", "height": "integer", "refresh": "integer"},
        "response": "{success: true, message: \"resolution updated\"}"
    },
    "rotate_display": {
        "method": "POST",
        "path": "/display/rotate",
        "description": "Rotate the display orientation.",
        "input": {"orientation": "normal|left|right|inverted"},
        "response": "{success: true, message: \"orientation set to left\"}"
    },
    "rotate_display_get": {
        "method": "GET",
        "path": "/display/rotate",
        "description": "Rotate the display orientation via query parameter.",
        "input": {"orientation": "normal|left|right|inverted"},
        "response": "{success: true, message: \"orientation set to left\"}"
    },
    "lock_screen_display": {
        "method": "POST",
        "path": "/display/lock",
        "description": "Lock the screen session.",
        "response": "{success: true, message: \"screen locked\"}"
    },
    "set_night_light": {
        "method": "POST",
        "path": "/display/night-light",
        "description": "Enable or disable night light and set temperature.",
        "input": {"enabled": "boolean", "temperature": "integer"},
        "response": "{success: true, message: \"night light updated\"}"
    },
    "get_network_ip": {
        "method": "GET",
        "path": "/network/ip",
        "description": "Return local and public IP addresses.",
        "response": "{local_ip: \"192.168.1.10\", public_ip: \"35.234.45.12\"}"
    },
    "get_wifi_status": {
        "method": "GET",
        "path": "/network/wifi/status",
        "description": "Return current WiFi connection status and available networks.",
        "response": "{connected: true, ssid: \"HomeWiFi\", networks: [...]}"
    },
    "list_wifi_networks": {
        "method": "GET",
        "path": "/network/wifi/list",
        "description": "List available WiFi networks.",
        "response": "{connected: true, ssid: \"HomeWiFi\", networks: [...]}"
    },
    "connect_wifi": {
        "method": "POST",
        "path": "/network/wifi/connect",
        "description": "Connect to a WiFi network.",
        "input": {"ssid": "string", "password": "string?"},
        "response": "{local_ip: \"192.168.1.10\", public_ip: \"35.234.45.12\"}"
    },
    "disconnect_wifi": {
        "method": "POST",
        "path": "/network/wifi/disconnect",
        "description": "Disconnect from WiFi.",
        "response": "{local_ip: \"127.0.0.1\", public_ip: null}"
    },
    "toggle_wifi": {
        "method": "POST",
        "path": "/network/wifi/toggle",
        "description": "Enable or disable WiFi radio.",
        "input": {"enabled": "boolean"},
        "response": "{local_ip: \"192.168.1.10\", public_ip: \"35.234.45.12\"}"
    },
    "toggle_bluetooth": {
        "method": "POST",
        "path": "/network/bluetooth/toggle",
        "description": "Enable or disable Bluetooth.",
        "input": {"enabled": "boolean"},
        "response": "{local_ip: \"192.168.1.10\", public_ip: \"35.234.45.12\"}"
    },
    "list_bluetooth_devices": {
        "method": "GET",
        "path": "/network/bluetooth/devices",
        "description": "List paired and available Bluetooth devices.",
        "response": "{devices: [{address: \"00:11:22:33:44:55\", name: \"Keyboard\"}]}"
    },
    "ping_host": {
        "method": "POST",
        "path": "/network/ping",
        "description": "Ping a host and return packet loss and average round-trip time.",
        "input": {"host": "string", "count": "integer 1-20"},
        "response": "{host: \"google.com\", packets_transmitted: 4, packets_received: 4, packet_loss: 0.0, avg_rtt_ms: 12.3}"
    },
    "list_files": {
        "method": "GET",
        "path": "/fs/list",
        "description": "List files and directories for a path.",
        "input": {"path": "string"},
        "response": "{files:[{name:\"file.txt\", path:\"/tmp/file.txt\", type:\"file\", size:1234, modified:1700000000}]}"
    },
    "download_file": {
        "method": "GET",
        "path": "/fs/download",
        "description": "Download a file from the filesystem.",
        "input": {"path": "string"},
        "response": "{path: \"/tmp/file.txt\", content_base64: \"...\", content_type: \"application/octet-stream\"}"
    },
    "upload_file": {
        "method": "POST",
        "path": "/fs/upload",
        "description": "Upload a file to a destination path.",
        "input": {"path": "string", "file_base64": "string"},
        "response": "{success: true, message: \"Uploaded file to /tmp/uploaded.txt\"}"
    },
    "delete_path": {
        "method": "DELETE",
        "path": "/fs/delete",
        "description": "Delete a file or directory.",
        "input": {"path": "string"},
        "response": "{success: true, message: \"Deleted /tmp/file.txt\"}"
    },
    "make_directory": {
        "method": "POST",
        "path": "/fs/mkdir",
        "description": "Create a new directory.",
        "input": {"path": "string"},
        "response": "{success: true, message: \"Created directory /tmp/newdir\"}"
    },
    "rename_path": {
        "method": "POST",
        "path": "/fs/rename",
        "description": "Rename or move a file or directory.",
        "input": {"from": "string", "to": "string"},
        "response": "{success: true, message: \"Renamed /tmp/a to /tmp/b\"}"
    },
    "search_files": {
        "method": "GET",
        "path": "/fs/search",
        "description": "Search files and directories by name.",
        "input": {"query": "string", "path": "string"},
        "response": "{files:[...]}"
    },
    "get_disk_usage": {
        "method": "GET",
        "path": "/fs/disk-usage",
        "description": "Return disk usage statistics for mounted partitions.",
        "response": "{usage:[{mountpoint:\"/\", total:100000000000, used:45000000000, free:45000000000, percent:45.0, filesystem:\"ext4\"}]}"
    },
    "zip_paths": {
        "method": "POST",
        "path": "/fs/zip",
        "description": "Create a zip archive from files and directories.",
        "input": {"paths": "array of strings", "output": "string"},
        "response": "{success: true, message: \"Created archive /tmp/archive.zip\"}"
    },
    "unzip_path": {
        "method": "POST",
        "path": "/fs/unzip",
        "description": "Extract a zip archive to a destination directory.",
        "input": {"path": "string", "destination": "string"},
        "response": "{success: true, message: \"Extracted archive to /tmp/dest\"}"
    },
    "open_path": {
        "method": "POST",
        "path": "/fs/open",
        "description": "Open a file or directory with the default system application.",
        "input": {"path": "string"},
        "response": "{success: true, message: \"Opened /tmp/file.txt\"}"
    },
    "move_mouse": {
        "method": "POST",
        "path": "/input/mouse/move",
        "description": "Move the mouse cursor to the given coordinates.",
        "input": {"x": "integer", "y": "integer"},
        "response": "{success: true, message: \"Mouse moved.\"}"
    },
    "click_mouse": {
        "method": "POST",
        "path": "/input/mouse/click",
        "description": "Click the mouse at the given coordinates.",
        "input": {"x": "integer", "y": "integer", "button": "left|right|middle"},
        "response": "{success: true, message: \"Mouse clicked.\"}"
    },
    "double_click_mouse": {
        "method": "POST",
        "path": "/input/mouse/double-click",
        "description": "Double-click the mouse at the given coordinates.",
        "input": {"x": "integer", "y": "integer"},
        "response": "{success: true, message: \"Mouse double-clicked.\"}"
    },
    "scroll_mouse": {
        "method": "POST",
        "path": "/input/mouse/scroll",
        "description": "Scroll the mouse wheel up or down.",
        "input": {"direction": "up|down", "amount": "integer"},
        "response": "{success: true, message: \"Mouse scrolled.\"}"
    },
    "type_keyboard": {
        "method": "POST",
        "path": "/input/keyboard/type",
        "description": "Type text using the keyboard.",
        "input": {"text": "string"},
        "response": "{success: true, message: \"Text typed.\"}"
    },
    "press_keyboard_keys": {
        "method": "POST",
        "path": "/input/keyboard/key",
        "description": "Press a keyboard key or key combination.",
        "input": {"keys": "array of strings"},
        "response": "{success: true, message: \"Keys pressed.\"}"
    },
    "clear_cache": {
        "method": "POST",
        "path": "/maintenance/clear-cache",
        "description": "Clear temporary and user cache directories.",
        "response": "{success: true, message: \"Cache cleared.\"}"
    },
    "get_logs": {
        "method": "GET",
        "path": "/maintenance/logs",
        "description": "Get the last N lines of a service journal log.",
        "input": {"service": "string", "lines": "integer"},
        "response": "{service: \"ssh.service\", lines: [\"...\"]}"
    },
    "check_updates": {
        "method": "GET",
        "path": "/maintenance/updates",
        "description": "Check for available system package updates.",
        "response": "{manager: \"apt\", updates: [...]}"
    },
    "run_update": {
        "method": "POST",
        "path": "/maintenance/update",
        "description": "Run a full system update after explicit confirmation.",
        "input": {"confirm": "boolean"},
        "response": "{success: true, message: \"System updated.\"}"
    },
    "sync_time": {
        "method": "POST",
        "path": "/maintenance/sync-time",
        "description": "Sync the system clock via NTP.",
        "response": "{success: true, message: \"Time synchronization enabled.\"}"
    },
    "list_services": {
        "method": "GET",
        "path": "/maintenance/services",
        "description": "List systemd services and their status.",
        "response": "{services:[...]}"
    },
    "restart_service": {
        "method": "POST",
        "path": "/maintenance/service/restart",
        "description": "Restart a systemd service.",
        "input": {"name": "string"},
        "response": "{success: true, message: \"Service nginx restarted.\"}"
    },
    "stop_service": {
        "method": "POST",
        "path": "/maintenance/service/stop",
        "description": "Stop a systemd service.",
        "input": {"name": "string"},
        "response": "{success: true, message: \"Service nginx stopped.\"}"
    },
    "start_service": {
        "method": "POST",
        "path": "/maintenance/service/start",
        "description": "Start a systemd service.",
        "input": {"name": "string"},
        "response": "{success: true, message: \"Service nginx started.\"}"
    },
    "play_pause": {
        "method": "POST",
        "path": "/media/play-pause",
        "description": "Toggle media playback on or off.",
        "response": "{success: true, message: \"playback toggled\"}"
    },
    "next_track": {
        "method": "POST",
        "path": "/media/next",
        "description": "Skip to the next media track.",
        "response": "{success: true, message: \"skipped to next track\"}"
    },
    "previous_track": {
        "method": "POST",
        "path": "/media/previous",
        "description": "Skip to the previous media track.",
        "response": "{success: true, message: \"skipped to previous track\"}"
    },
    "seek_media": {
        "method": "POST",
        "path": "/media/seek",
        "description": "Seek media playback to a specified position in seconds.",
        "input": {"seconds": "number"},
        "response": "{success: true, message: \"seeked playback\"}"
    },
    "now_playing": {
        "method": "GET",
        "path": "/media/now-playing",
        "description": "Return current media metadata and playback position.",
        "response": "{title: \"Song\", artist: \"Artist\", status: \"Playing\"}"
    },
    "monitor_snapshot": {
        "method": "GET",
        "path": "/monitor/snapshot",
        "description": "Return a live metrics snapshot for CPU, RAM, GPU, disk I/O, network I/O, temperatures, fans, battery, and processes.",
        "response": "{cpu: {...}, ram: {...}, gpu: [...], disk_io: [...], network_io: [...], temperatures: [...], fans: [...], battery: {...}, processes: {...}}"
    },
    "monitor_cpu": {
        "method": "GET",
        "path": "/monitor/cpu",
        "description": "Return CPU usage percentages.",
        "response": "{overall: 12.5, per_core: [10.0, 15.0, 12.0, 13.0]}"
    },
    "monitor_ram": {
        "method": "GET",
        "path": "/monitor/ram",
        "description": "Return RAM and swap usage status.",
        "response": "{total: 17179869184, available: 8320000000, used: 8340000000, percent: 48.5, swap_total: 2147483648, swap_used: 0, swap_free: 2147483648, swap_percent: 0.0}"
    },
    "monitor_gpu": {
        "method": "GET",
        "path": "/monitor/gpu",
        "description": "Return GPU utilization and memory usage.",
        "response": "[{name: \"NVIDIA RTX\", utilization_percent: 35.0, memory_used_mb: 2048, memory_total_mb: 8192}]"
    },
    "monitor_disk_io": {
        "method": "GET",
        "path": "/monitor/disk-io",
        "description": "Return current per-disk I/O rates.",
        "response": "[{device: \"sda\", read_bytes_per_sec: 1024.0, write_bytes_per_sec: 512.0}]"
    },
    "monitor_network_io": {
        "method": "GET",
        "path": "/monitor/network-io",
        "description": "Return current network I/O rates per interface.",
        "response": "[{interface: \"eth0\", bytes_sent_per_sec: 10240.0, bytes_recv_per_sec: 20480.0}]"
    },
    "monitor_temperatures": {
        "method": "GET",
        "path": "/monitor/temperatures",
        "description": "Return sensor temperature readings.",
        "response": "[{sensor: \"coretemp\", label: \"Package id 0\", current: 42.0, high: 100.0, critical: 105.0}]"
    },
    "monitor_fans": {
        "method": "GET",
        "path": "/monitor/fans",
        "description": "Return fan speed sensor readings.",
        "response": "[{sensor: \"fan1\", speed_rpm: 1200}]"
    },
    "monitor_battery": {
        "method": "GET",
        "path": "/monitor/battery",
        "description": "Return battery percentage, plugged state, and remaining seconds.",
        "response": "{percent: 87.0, plugged_in: true, secs_left: 14000}"
    },
    "monitor_processes": {
        "method": "GET",
        "path": "/monitor/processes",
        "description": "Return top processes by CPU and memory.",
        "response": "{top_by_cpu:[...], top_by_memory:[...]}"
    },
    "list_processes": {
        "method": "GET",
        "path": "/processes",
        "description": "List running processes with CPU and memory usage.",
        "response": "{processes:[...]}"
    },
    "kill_process": {
        "method": "DELETE",
        "path": "/processes/{pid}",
        "description": "Terminate a process by PID.",
        "input": {"pid": "integer"},
        "response": "{success: true, message: \"Process 123 terminated.\"}"
    },
    "kill_process_by_name": {
        "method": "DELETE",
        "path": "/processes/name/{name}",
        "description": "Terminate all processes matching a name.",
        "input": {"name": "string"},
        "response": "{success: true, message: \"Killed 2 process(es).\", killed_count: 2}"
    },
    "launch_process": {
        "method": "POST",
        "path": "/processes/launch",
        "description": "Launch a new process with optional arguments.",
        "input": {"command": "string", "args": "array of strings"},
        "response": "{success: true, message: \"Process launched.\", pid: 4321}"
    },
    "active_window": {
        "method": "GET",
        "path": "/processes/active-window",
        "description": "Return the currently focused window title.",
        "response": "{window_id: \"12345\", title: \"Terminal\"}"
    },
    "minimize_window": {
        "method": "POST",
        "path": "/processes/window/minimize",
        "description": "Minimize a window by ID.",
        "input": {"window_id": "string"},
        "response": "{success: true, message: \"Window minimized.\"}"
    },
    "close_window": {
        "method": "POST",
        "path": "/processes/window/close",
        "description": "Close a window by ID.",
        "input": {"window_id": "string"},
        "response": "{success: true, message: \"Window closed.\"}"
    },
    "lock_session": {
        "method": "POST",
        "path": "/security/lock",
        "description": "Lock the screen session.",
        "response": "{success: true, message: \"Screen locked.\"}"
    },
    "logout_user": {
        "method": "POST",
        "path": "/security/logout",
        "description": "Log out the current user session.",
        "response": "{success: true, message: \"User logged out.\"}"
    },
    "disable_webcam": {
        "method": "POST",
        "path": "/security/webcam/disable",
        "description": "Disable the webcam.",
        "response": "{success: true, message: \"Webcam disabled.\"}"
    },
    "enable_webcam": {
        "method": "POST",
        "path": "/security/webcam/enable",
        "description": "Enable the webcam.",
        "response": "{success: true, message: \"Webcam enabled.\"}"
    },
    "webcam_snapshot": {
        "method": "POST",
        "path": "/security/webcam/snapshot",
        "description": "Capture a webcam image and return it as base64.",
        "response": "{image_base64: \"...\"}"
    },
    "disable_mic": {
        "method": "POST",
        "path": "/security/mic/disable",
        "description": "Disable the default microphone.",
        "response": "{success: true, message: \"Microphone disabled.\"}"
    },
    "enable_mic": {
        "method": "POST",
        "path": "/security/mic/enable",
        "description": "Enable the default microphone.",
        "response": "{success: true, message: \"Microphone enabled.\"}"
    },
    "get_login_history": {
        "method": "GET",
        "path": "/security/login-history",
        "description": "Return recent login history events.",
        "response": "{events:[...]}"
    },
    "get_ssh_sessions": {
        "method": "GET",
        "path": "/security/ssh-sessions",
        "description": "Return active SSH sessions.",
        "response": "{sessions:[...]}"
    },
    "schedule_job": {
        "method": "POST",
        "path": "/scheduler/create",
        "description": "Schedule a command to run at a specific time or on a cron schedule.",
        "input": {"command": "string", "args": "array of strings", "run_at": "ISO datetime", "recurring": "string?"},
        "response": "{success: true, message: \"Scheduled job ...\"}"
    },
    "list_jobs": {
        "method": "GET",
        "path": "/scheduler/list",
        "description": "List all scheduled tasks.",
        "response": "{jobs:[...]}"
    },
    "cancel_job": {
        "method": "DELETE",
        "path": "/scheduler/cancel/{task_id}",
        "description": "Cancel a scheduled task.",
        "input": {"task_id": "string"},
        "response": "{success: true, message: \"Cancelled task ...\"}"
    },
    "run_job_now": {
        "method": "POST",
        "path": "/scheduler/run-now/{task_id}",
        "description": "Trigger a scheduled task immediately.",
        "input": {"task_id": "string"},
        "response": "{success: true, message: \"Triggered task ...\"}"
    },
    "send_notification": {
        "method": "POST",
        "path": "/notifications/send",
        "description": "Send a desktop notification.",
        "input": {"title": "string", "message": "string", "app_name": "string?", "urgency": "low|normal|critical?"},
        "response": "{id: 1, title: \"Hello\", message: \"World\", app_name: \"Vela\", urgency: \"normal\", timestamp: 1700000000.0}"
    },
    "clear_notifications": {
        "method": "POST",
        "path": "/notifications/clear",
        "description": "Clear agent-tracked notifications and attempt to clear desktop notifications.",
        "response": "{success: true}"
    },
    "read_notifications": {
        "method": "GET",
        "path": "/notifications/read",
        "description": "Read notifications sent through this agent.",
        "response": "{notifications:[...]}"
    },
    "list_notifications": {
        "method": "GET",
        "path": "/notifications/list",
        "description": "List desktop notification history.",
        "response": "{notifications:[...]}"
    },
    "power_shutdown": {
        "method": "POST",
        "path": "/power/shutdown",
        "description": "Shut down the machine.",
        "response": "{success: true, message: \"shutdown initiated\"}"
    },
    "power_restart": {
        "method": "POST",
        "path": "/power/restart",
        "description": "Restart the machine.",
        "response": "{success: true, message: \"restart initiated\"}"
    },
    "power_sleep": {
        "method": "POST",
        "path": "/power/sleep",
        "description": "Put the machine to sleep.",
        "response": "{success: true, message: \"sleep initiated\"}"
    },
    "power_hibernate": {
        "method": "POST",
        "path": "/power/hibernate",
        "description": "Hibernate the machine.",
        "response": "{success: true, message: \"hibernate initiated\"}"
    },
}

SYSTEM_TOOL_PROMPT = """
You are Vela, a precise Linux PC controller. You may only use the tools listed below when the user asks for system state or actions.
Use the exact tool names and expected input shapes.
When you need to fetch or change state, return ONLY a JSON object with these fields:
{
  "tool": "<tool_name>",
  "tool_input": { ... }
}
If no tool call is required, return:
{
  "tool": "none",
  "tool_input": {}
}

Available tools:
"""

SYSTEM_TOOL_PROMPT += "\n".join(
    f"- {name}: {tool['description']} Response shape: {tool.get('response', '{}')} Input: {tool.get('input', '{}')}"
    for name, tool in TOOL_DEFINITIONS.items()
)

SYSTEM_TOOL_PROMPT += "\n\nAlways return valid JSON and nothing else. Do not explain yourself in the tool selection response."

FINAL_RESPONSE_PROMPT = """
You are Vela. The user asked a question and the tool returned a JSON response.
Craft a concise, accurate answer in clean Markdown using the tool response data.
Do not return raw JSON or tool metadata.
If the tool response contains an error, summarize the failure clearly.
"""


class AssistantRequest(BaseModel):
    message: str


class AssistantResponse(BaseModel):
    reply: str


def _dict_get(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _clean_assistant_text(text: str) -> str:
    if not text:
        return ""
    cleaned = text.strip()
    cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*```$', '', cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()
    return cleaned


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
            return _clean_assistant_text(str(text))
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
                return _clean_assistant_text(str(content))
    if isinstance(response_data, dict):
        return _clean_assistant_text(json.dumps(response_data))
    return _clean_assistant_text(str(response_data))


def _set_dashscope_base_url() -> None:
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


def _extract_json_object(text: str) -> dict[str, Any] | None:
    cleaned = _clean_assistant_text(text)
    # Find first JSON object in the response.
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        return None
    candidate = match.group(0)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        try:
            # Attempt to fix trailing commas
            candidate = re.sub(r",\s*}\s*$", "}", candidate)
            candidate = re.sub(r",\s*\]\s*$", "]", candidate)
            return json.loads(candidate)
        except json.JSONDecodeError:
            return None

INPUT_CONFIRM_TOOLS = {
    "move_mouse",
    "click_mouse",
    "double_click_mouse",
    "scroll_mouse",
    "type_keyboard",
    "press_keyboard_keys",
}


def _plan_tool_call(user_message: str) -> dict[str, Any]:
    _set_dashscope_base_url()
    messages = [
        {"role": "system", "content": SYSTEM_TOOL_PROMPT},
        {"role": "user", "content": user_message},
    ]
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
    parsed = _extract_json_object(text)
    if not parsed or "tool" not in parsed or "tool_input" not in parsed:
        raise ValueError(f"Could not parse tool selection from model output: {text}")
    return parsed


async def _execute_tool(app: FastAPI, tool_name: str, tool_input: dict[str, Any], auth_header: str | None) -> dict[str, Any]:
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
    if tool_name not in {"upload_file"}:
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
            file_bytes = base64.b64decode(file_base64)
            response = await client.post(
                path,
                data={"path": path_value},
                files={"file": ("upload.bin", file_bytes, "application/octet-stream")},
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


def _compose_final_reply(user_message: str, tool_name: str, tool_response: dict[str, Any]) -> str:
    final_system = "You are Vela. The user asked for information or an action. Use the tool response data to produce a concise Markdown answer. Do not return raw JSON."
    content = (
        f"User request: {user_message}\n\n"
        f"Tool: {tool_name}\n"
        f"Tool response: {json.dumps(tool_response, indent=2)}\n"
        "Answer the user in clean Markdown."
    )
    messages = [
        {"role": "system", "content": final_system},
        {"role": "user", "content": content},
    ]
    response = Generation.call(
        api_key=_get_api_key(),
        model=config.dashscope_model,
        messages=messages,
        result_format="message",
        stream=False,
        incremental_output=False,
        temperature=0.2,
        max_tokens=512,
    )
    return _get_response_text(response)


@router.post("/chat", response_model=AssistantResponse, dependencies=[Depends(get_current_user)])
async def chat(body: AssistantRequest, request: Request) -> AssistantResponse:
    auth_header = request.headers.get("authorization")
    tool_call = None
    try:
        tool_call = _plan_tool_call(body.message)
    except Exception as exc:
        logger.error("Tool planning failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail=str(exc))

    tool_name = tool_call.get("tool")
    tool_input = tool_call.get("tool_input") or {}
    if tool_name == "none":
        return AssistantResponse(reply="I'm not sure which tool is needed for that request.")

    try:
        tool_response = await _execute_tool(request.app, tool_name, tool_input, auth_header)
    except Exception as exc:
        logger.error("Tool execution failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail=str(exc))

    try:
        final_text = _compose_final_reply(body.message, tool_name, tool_response)
    except Exception as exc:
        logger.error("Final response composition failed: %s", exc, exc_info=True)
        final_text = json.dumps(tool_response)

    return AssistantResponse(reply=final_text.strip())
