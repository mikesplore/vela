# Phase 3 Response Models

This file documents the validated response shapes for phase 3 endpoints in the Vela API.
It is based on the current implementation in `routers/display.py`, `routers/audio.py`, and `routers/power.py`.

## `/display` endpoints

### `GET /display/screenshot`
```json
{
  "image_base64": "<base64-encoded-png>"
}
```

> Note: this endpoint uses `gnome-screenshot` for screenshots. Install `gnome-screenshot` and ensure it is available in PATH.

### `POST /display/record`
Request body:
```json
{
  "duration_seconds": 10
}
```
Response:
```json
{
  "image_base64": "<base64-encoded-mp4>"
}
```

### `POST /display/monitor/off`
```json
{
  "success": true,
  "message": "monitor off"
}
```

### `POST /display/monitor/on`
```json
{
  "success": true,
  "message": "monitor on"
}
```

### `GET /display/brightness`
```json
{
  "brightness": 65.0
}
```
`brightness` may be `null` if it cannot be determined.

### `POST /display/brightness`
Request body:
```json
{
  "value": 70
}
```
Response:
```json
{
  "success": true,
  "message": "brightness set to 70"
}
```

### `GET /display/resolution`
```json
{
  "width": 1920,
  "height": 1080,
  "refresh": 60.0,
  "output": "HDMI-1"
}
```

### `POST /display/resolution`
Request body:
```json
{
  "width": 1920,
  "height": 1080,
  "refresh": 60
}
```
Response:
```json
{
  "success": true,
  "message": "resolution updated"
}
```

### `POST /display/rotate`
Request body:
```json
{
  "orientation": "left"
}
```
Response:
```json
{
  "success": true,
  "message": "orientation set to left"
}
```

### `GET /display/rotate?orientation=<orientation>`
Same response shape as `POST /display/rotate`.

### `POST /display/lock`
```json
{
  "success": true,
  "message": "screen locked"
}
```

### `POST /display/night-light`
Request body:
```json
{
  "enabled": true,
  "temperature": 4500
}
```
Response:
```json
{
  "success": true,
  "message": "night light updated"
}
```

## `/audio` endpoints

### `GET /audio/volume`
```json
{
  "volume": 74,
  "muted": false
}
```

### `POST /audio/volume`
Request body:
```json
{
  "value": 60
}
```
Response shape is the same as `GET /audio/volume`.

### `POST /audio/volume/up`
Request body:
```json
{
  "step": 5
}
```
Response shape is the same as `GET /audio/volume`.

### `GET /audio/volume/up?step=5`
Same response shape as `POST /audio/volume/up`.

### `POST /audio/volume/down`
Request body:
```json
{
  "step": 5
}
```
Response shape is the same as `GET /audio/volume`.

### `GET /audio/volume/down?step=5`
Same response shape as `POST /audio/volume/down`.

### `POST /audio/mute`
Request body:
```json
{
  "muted": true
}
```
Response shape is the same as `GET /audio/volume`.

> Note: a `422 Unprocessable Content` means the request body was missing or invalid. You must send JSON with the `muted` field.

### `GET /audio/mute?muted=true`
Same response shape as `POST /audio/mute`.

### `GET /audio/devices`
```json
[
  {
    "id": "0",
    "name": "alsa_output.test",
    "type": "sink"
  },
  {
    "id": "0",
    "name": "alsa_input.test",
    "type": "source"
  }
]
```

### `GET /audio/output-devices`
Alias for `/audio/devices`, same response shape.

### `POST /audio/output-device`
Request body:
```json
{
  "device_id": "alsa_output.test"
}
```
Response shape is the same as `GET /audio/volume`.

### `GET /audio/output-device?device_id=<id>`
Same response shape as `POST /audio/output-device`.

## `/power` endpoints

### `POST /power/shutdown`
```json
{
  "success": true,
  "message": "shutdown initiated"
}
```

### `POST /power/restart`
```json
{
  "success": true,
  "message": "restart initiated"
}
```

### `POST /power/sleep`
```json
{
  "success": true,
  "message": "sleep initiated"
}
```

### `POST /power/hibernate`
```json
{
  "success": true,
  "message": "hibernate initiated"
}
```

## Notes

- `GET /display/brightness` may return `brightness: null` if brightness cannot be detected.
- `GET /audio/devices` returns both sink and source audio devices.
- `GET /audio/output-device` and `POST /audio/output-device` require `device_id`.
- `POST /display/record` and `/display/screenshot` return base64-encoded binary payloads.
- `POST /display/monitor/off` and `/display/monitor/on` return a generic success object.
