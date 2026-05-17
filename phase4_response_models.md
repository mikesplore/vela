# Phase 4 Response Models

This file documents the validated response structures for phase 4 endpoints in the Vela API.
It is based on the implemented behavior in `routers/notifications.py`, `routers/clipboard.py`, and `routers/media.py`.

## `/notifications` endpoints

### `POST /notifications/send`
Request body:
```json
{
  "title": "Hello",
  "message": "World",
  "app_name": "Vela",
  "urgency": "normal"
}
```
Response:
```json
{
  "id": 1,
  "title": "Hello",
  "message": "World",
  "app_name": "Vela",
  "urgency": "normal",
  "timestamp": 1700000000.0
}
```

### `POST /notifications/clear`
```json
{
  "success": true
}
```

### `GET /notifications/read`
```json
{
  "notifications": [
    {
      "id": 1,
      "title": "Hello",
      "message": "World",
      "app_name": "Vela",
      "urgency": "normal",
      "timestamp": 1700000000.0
    }
  ]
}
```

### `GET /notifications/list`
Same response shape as `GET /notifications/read`.

## `/clipboard` endpoints

### `GET /clipboard/read`
```json
{
  "text": "clipboard contents"
}
```

### `POST /clipboard/write`
Request body:
```json
{
  "text": "clipboard contents"
}
```
Response:
```json
{
  "success": true,
  "message": "clipboard updated"
}
```

### `POST /clipboard/clear`
```json
{
  "success": true,
  "message": "clipboard cleared"
}
```

## `/media` endpoints

### `POST /media/play-pause`
```json
{
  "success": true,
  "message": "playback toggled"
}
```

### `POST /media/next`
```json
{
  "success": true,
  "message": "skipped to next track"
}
```

### `POST /media/previous`
```json
{
  "success": true,
  "message": "skipped to previous track"
}
```

### `POST /media/seek`
Request body:
```json
{
  "seconds": 90.0
}
```
Response:
```json
{
  "success": true,
  "message": "seeked playback"
}
```

### `GET /media/now-playing`
```json
{
  "title": "Test Song",
  "artist": "Test Artist",
  "album": "Test Album",
  "art_url": "https://i.scdn.co/image/test",
  "status": "Playing",
  "position_seconds": 42.0,
  "length_seconds": 120.0
}
```

## Notes

- `/notifications/list` may return actual desktop notification history if `dunstctl` is available; otherwise it returns the agent-tracked list.
- `/clipboard/read` returns the current clipboard text as plain string content.
- `/media/now-playing` will populate only the fields it can query via `playerctl`; missing values may be `null`.
- All phase 4 endpoints require JWT auth via `Authorization: Bearer <token>`.
