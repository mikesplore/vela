# Changelog

## Unreleased

- Phase 1: initialized project skeleton with FastAPI app, config loading from `config.yaml`, JWT authentication, request logging middleware, IP allowlist middleware, public `/health` and `/` endpoints, and systemd service definition under the Vela brand.
- Added authentication tests for token issuance, invalid credentials, expired tokens, and missing credentials.
- Phase 2: added system information and live monitoring endpoints with JWT protection, including snapshot, CPU, RAM, GPU, disk, network, temperatures, fans, battery, and websocket streaming support.
- Phase 3: added display, audio, and power control endpoints for screenshots, brightness, resolution, volume, mute, audio devices, shutdown, restart, suspend, and hibernate.
- Phase 4: added notifications, clipboard, and media control endpoints for sending notifications, clipboard read/write/clear, playback toggle, next/previous track, seek, and now-playing metadata.
- Phase 5: added processes, input control, and security endpoints for process management, window control, guarded mouse and keyboard input, screen lock/logout, webcam and microphone toggling, login history, and SSH session discovery.
