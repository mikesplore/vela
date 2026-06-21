# Vela Agent — API Documentation (Implemented Endpoints)

This file documents the implemented HTTP endpoints in this repository, the expected request shapes, required headers, and example responses. All endpoints (unless noted) require an `Authorization: Bearer <token>` header returned by `POST /auth/token`.

---

**Auth**

- POST /auth/token
  - Auth: none
  - Request JSON: { "username": "...", "password": "..." }
  - Response JSON: { "access_token": "<jwt>", "token_type": "bearer", "expires_at": "2026-...Z" }

---

**General**

- GET /health
  - Auth: none
  - Response JSON: { "status": "ok", "uptime_seconds": 123 }

- GET /ping
  - Auth: none
  - Response JSON: { "pong": true }

- GET /
  - Auth: none
  - Response JSON: { "name": "Vela", "version": "1.0.0", "enabled_modules": ["display","audio",...] }

---

**Display** (prefix: /display)

- GET /display/screenshot
  - Headers: `Authorization`
  - Request: none
  - Response: { "image_base64": "<base64 PNG>" }

- POST /display/record
  - Headers: `Authorization`
  - Request JSON: { "duration_seconds": 10 }
  - Response: { "image_base64": "<base64 MP4>" }

- POST /display/monitor/off
  - Request: none
  - Response: { "success": true, "message": "monitor off (... )" }

- POST /display/monitor/on
  - Response: { "success": true, "message": "monitor on (...)" }

- GET /display/brightness
  - Response: { "brightness": 75.0 }

- POST /display/brightness
  - Request JSON: { "value": 0-100 }
  - Response: { "success": true, "message": "brightness set to 70" }

- GET /display/resolution
  - Response: { "width": 1920, "height": 1080, "refresh": 60.0, "output": "HDMI-1" }

- POST /display/resolution
  - Request JSON: { "width": 1920, "height": 1080, "refresh": 60 }
  - Response: { "success": true, "message": "resolution updated" }

- POST /display/rotate
  - Request JSON: { "orientation": "normal|left|right|inverted" }
  - Response: { "success": true, "message": "orientation set to left" }

- GET /display/rotate?orientation=left
  - Proxy to POST rotate.

- POST /display/lock
  - Response: { "success": true, "message": "screen locked" }

- POST /display/night-light
  - Request JSON: { "enabled": true, "temperature": 4000 } (temperature: 1000–10000 Kelvin; omit for no change)
  - Response: { "success": true, "message": "night light updated" }

---

**Audio** (prefix: /audio)

- GET /audio/volume
  - Response JSON: { "volume": 60, "muted": false }

- POST /audio/volume
  - Request JSON: { "value": 0-100 }
  - Response: { "volume": 60, "muted": false }

- POST /audio/volume/up
  - Request JSON: { "step": 5 }
  - Response: { "volume": 65, "muted": false }

- GET /audio/volume/up?step=5
  - Same as POST variant.

- POST /audio/volume/down
  - Request JSON: { "step": 5 }
  - Response: { "volume": 55, "muted": false }

- POST /audio/mute
  - Request JSON: { "muted": true }
  - Response: { "volume": 55, "muted": true }

- GET /audio/devices
  - Response: [ { "id": "0", "name": "HDMI Output", "type": "sink" }, ... ]

- POST /audio/output-device
  - Request JSON: { "device_id": "..." }
  - Response: { "volume": 60, "muted": false }

- GET /audio/output-device?device_id=alsa_output.pci-... (alias)

- POST /audio/beep
  - Response: { "success": true, "message": "beep played" }

Note: `/audio/input-device` is not implemented; microphone mute is in `/security`.

---

**Power** (prefix: /power)

- POST /power/shutdown
  - Request JSON (not required): optional { "delay_seconds": 0 } (repo uses immediate systemctl)
  - Response: { "success": true, "message": "shutdown initiated" }

- POST /power/restart
  - Response: { "success": true, "message": "restart initiated" }

- POST /power/sleep
  - Response: { "success": true, "message": "sleep initiated" }

- POST /power/hibernate
  - Response: { "success": true, "message": "hibernate initiated" }

- POST /power/schedule-shutdown
  - Request JSON: { "at": "2025-12-01T23:00:00" }
  - Response: { "success": true, "message": "shutdown scheduled for 2025-12-01 23:00" }

- POST /power/cancel-shutdown
  - Response: { "success": true, "message": "shutdown canceled" }

- GET /power/profile
  - Response: { "success": true, "message": "current power profile retrieved", "profile": "balanced" }

- POST /power/profile
  - Request JSON: { "profile": "performance" }
  - Response: { "success": true, "message": "profile set to performance", "profile": "performance" }

---

**Filesystem** (prefix: /fs)

- GET /fs/list?path=/home/user
  - Response: Tree-friendly directory listing with parent navigation:
    ```json
    {
      "files": [
        {
          "name": "folder1",
          "path": "/home/user/folder1",
          "type": "directory",
          "size": 4096,
          "modified": 1634567890.0,
          "has_children": true,
          "children_count": 5
        },
        {
          "name": "file.txt",
          "path": "/home/user/file.txt",
          "type": "file",
          "size": 1234,
          "modified": 1634567890.0,
          "extension": ".txt"
        }
      ],
      "current_path": "/home/user",
      "parent_path": "/home",
      "total_items": 2
    }
    ```
  - Folders appear first (sorted), followed by files
  - `has_children` & `children_count`: for folders only (indicates if folder can be explored)
  - `parent_path`: for easy upward navigation in tree
  - `extension`: for files only (file type indicator)

- GET /fs/tree?path=/home/user&max_depth=1
  - Hierarchical tree structure for folder visualization:
    ```json
    {
      "root": {
        "name": "user",
        "path": "/home/user",
        "type": "directory",
        "has_children": true,
        "children_count": 15
      },
      "children": [
        {"name": "folder1", "path": "...", "type": "directory", "has_children": true, "children_count": 5},
        {"name": "file.txt", "path": "...", "type": "file", "has_children": false, "children_count": 0}
      ],
      "breadcrumbs": [
        {"name": "/", "path": "/"},
        {"name": "home", "path": "/home"},
        {"name": "user", "path": "/home/user"}
      ]
    }
    ```
  - `breadcrumbs`: Full path navigation for tree UI
  - `max_depth`: 1-3 for performance optimization
  - Ideal for building interactive file explorers

- GET /fs/download?path=/home/user/file.txt
  - Response: binary file download (Content-Disposition attachment).

- POST /fs/upload (multipart)
  - Form field `path` and file field. Example using multipart form: `path=/home/user/uploads` and file data.
  - Response: { "success": true, "message": "Uploaded file to /..." }

- DELETE /fs/delete
  - Request JSON: { "path": "/home/user/tmp" }
  - Response: { "success": true, "message": "Deleted /..." }

- POST /fs/mkdir
  - Request JSON: { "path": "/home/user/newdir" }
  - Response: { "success": true, "message": "Created directory /..." }

- POST /fs/rename
  - Request JSON: { "from": "/from/path", "to": "/to/path" }
  - Response: { "success": true, "message": "Renamed ..." }

- GET /fs/search?query=report&path=/home
  - Response: same shape as /fs/list with matching files and folders (tree-enabled).

- GET /fs/disk-usage
  - Response: { "usage": [ { "mountpoint":"/","total":...,"used":...,"free":...,"percent":...,"filesystem":"ext4" }, ... ] }

- POST /fs/zip
  - Request JSON: { "paths": ["/a","/b"], "output": "/out/archive.zip" }
  - Response: { "success": true, "message": "Created archive /out/archive.zip" }

- POST /fs/unzip
  - Request JSON: { "path": "/out/archive.zip", "destination": "/tmp/extract" }
  - Response: { "success": true, "message": "Extracted archive to /tmp/extract" }

- POST /fs/open
  - Request JSON: { "path": "/home/user/file.pdf" }
  - Response: { "success": true, "message": "Opened /..." }

Security: `config.allowed_base_dirs` is enforced; requests outside allowed directories return HTTP 403.

---

**Network** (prefix: /network)

- GET /network/ip
  - Response: { "local_ip": "192.168.1.5", "public_ip": "1.2.3.4" }

- GET /network/location
  - Response: { "local_ip": "...", "public_ip": "...", "location": { "country": "...", "city": "...", "lat": .., "lon": .. } }

- GET /network/wifi/status and /network/wifi/list
  - Response: { "connected": true, "ssid": "MyNet", "device": null, "signal": 70, "networks": [ { "ssid":"...","signal":... } ] }

- POST /network/wifi/connect
  - Request JSON: { "ssid": "MyNet", "password": "pw" }
  - Response: { "local_ip": "...", "public_ip": "..." }

- POST /network/wifi/disconnect
  - Response: { "local_ip": "...", "public_ip": "..." }

- POST /network/wifi/toggle
  - Request JSON: { "enabled": true }
  - Response: { "local_ip": "...", "public_ip": "..." }

- POST /network/ping
  - Request JSON: { "host": "8.8.8.8", "count": 4 }
  - Response: { "host":"8.8.8.8","packets_transmitted":4,"packets_received":4,"packet_loss":0.0,"avg_rtt_ms":12.3 }

- GET /network/speed-test
  - Response: { "download_mbps": 100.3, "upload_mbps": 12.4, "ping_ms": 18.2 }

- Bluetooth endpoints: /network/bluetooth/devices, /network/bluetooth/pair, /network/bluetooth/unpair — standard request/response shapes as defined by models.

---

**Notifications** (prefix: /notifications)

- POST /notifications/send
  - Request JSON: { "title":"Hi","message":"Hello","urgency":"normal","app_name":"MyApp" }
  - Response JSON: { "id": 1, "title": "Hi", "message": "Hello", "app_name": "MyApp", "urgency":"normal", "timestamp": 167... }

- POST /notifications/clear
  - Response: { "success": true }

- GET /notifications/read
  - Response: { "notifications": [ {...}, ... ] }

- GET /notifications/list
  - Response: system history or agent-tracked notifications list.

---

**Clipboard** (prefix: /clipboard)

- GET /clipboard/read
  - Response: { "data": "clipboard text" }

- POST /clipboard/write
  - Request JSON: { "text": "..." }
  - Response: { "success": true, "message": "clipboard updated" }

- POST /clipboard/clear
  - Response: { "success": true }

---

**Media** (prefix: /media)

- POST /media/play-pause
  - Response: { "success": true, "message": "playback toggled" }

- POST /media/next
  - Response: { "success": true, "message": "skipped to next track" }

- POST /media/previous
  - Response: { "success": true, "message": "skipped to previous track" }

- POST /media/seek
  - Request JSON: { "seconds": 90 }
  - Response: { "success": true, "message": "seeked playback" }

- GET /media/now-playing
  - Response: { "title":"Title","artist":"Artist","album":"Album","status":"Playing","position_seconds":30.1,"length_seconds":240 }

Note: `/media/stop` not implemented.

---

**Processes** (prefix: /processes)

- GET /processes
  - Response: list of process entries: { "pid": 123, "name":"proc", "cpu": 0.5, "mem": 12.3 }

- DELETE /processes/{pid}
  - Response: { "success": true, "message": "killed pid 123" }

- DELETE /processes/name/{name}
  - Response: { "success": true, "message": "killed processes named xyz" }

- POST /processes/launch
  - Request JSON: { "command": "/usr/bin/gedit", "args": ["file.txt"] }
  - Response: { "success": true, "message": "launched" }

- GET /processes/active-window
  - Response: { "window_id": "1234", "title": "Window Title", "app_name": "/path/to/executable" }

- POST /processes/window/minimize and /processes/window/close
  - Request JSON: { "window_id": "..." }
  - Response: { "success": true }

---

**Input Control** (prefix: /input)

- NOTE: All endpoints require `Authorization` AND header `X-Confirm-Input: true`.

- POST /input/mouse/move
  - Request JSON: { "x": 500, "y": 300 }
  - Response: { "success": true, "message": "Mouse moved." }

- POST /input/mouse/click
  - Request JSON: { "x":500, "y":300, "button":"left|right|middle" }
  - Response: { "success": true }

- POST /input/mouse/double-click, /mouse/scroll
  - Request JSON: respectively { "x", "y" } or { "direction":"up|down","amount":3 }

- POST /input/keyboard/type
  - Request JSON: { "text": "hello" }

- POST /input/keyboard/key
  - Request JSON: { "keys": ["ctrl","c"] }

---

**Security** (prefix: /security)

- POST /security/lock
  - Response: { "success": true, "message": "locked" }

- POST /security/logout
  - Response: { "success": true }

- POST /security/webcam/disable and /security/webcam/enable
  - Response: { "success": true, "message": "webcam disabled/enabled" }

- POST /security/webcam/snapshot
  - Response: { "image_base64": "<base64 jpg>" }

- POST /security/mic/disable and /security/mic/enable
  - Response: { "success": true }

- GET /security/login-history
  - Response: { "events": [ { "when": 167..., "user":"...", "type":"login" }, ... ] }

- GET /security/ssh-sessions
  - Response: { "sessions": [ { "pid":..., "user":"...", "remote":"1.2.3.4" }, ... ] }

---

**Scheduler** (prefix: /scheduler)

- POST /scheduler/create
  - Request JSON: { "command":"...", "run_at":"2026-06-02T23:00:00Z", "recurring": null }
  - Response: { "id": "task-uuid", "next_run": "..." }

- GET /scheduler/list
  - Response: list of scheduled tasks

- DELETE /scheduler/cancel/{task_id}
  - Response: { "success": true, "message": "canceled" }

- POST /scheduler/run-now/{task_id}
  - Response: { "success": true, "message": "triggered" }

---

**Maintenance** (prefix: /maintenance)

- POST /maintenance/clear-cache
  - Response: { "success": true, "message": "cache cleared" }

- GET /maintenance/logs?service=nginx&lines=100
  - Response: { "service": "nginx", "lines": ["...", ...] }

- GET /maintenance/updates
  - Response: { "updates_available": true, "packages": [ ... ] }

- POST /maintenance/update
  - Response: { "success": true, "message": "update started" }

- POST /maintenance/sync-time
  - Response: { "success": true }

- GET /maintenance/services
  - Response: { "services": [ { "name":"sshd", "active": true }, ... ] }

- POST /maintenance/service/restart|stop|start
  - Request JSON: { "name": "service.name" }
  - Response: { "success": true }

---

If you want, I can also:
- generate a full OpenAPI JSON subset for these implemented routes (suitable for generating client SDKs), or
- produce a Postman collection / example `httpx` client snippets for auth + a selected module (e.g., file browsing + download + upload).

Tell me which output you prefer and I will add it to the repo (e.g., `openapi_subset.json` or `postman_collection.json`).
