# Changelog

## Unreleased

- Phase 1: initialized project skeleton with FastAPI app, config loading from `config.yaml`, JWT authentication, request logging middleware, IP allowlist middleware, public `/health` and `/` endpoints, and systemd service definition under the Vela brand.
- Added authentication tests for token issuance, invalid credentials, expired tokens, and missing credentials.
- Phase 2: added system information and live monitoring endpoints with JWT protection, including snapshot, CPU, RAM, GPU, disk, network, temperatures, fans, battery, and websocket streaming support.
- Phase 3: added display, audio, and power control endpoints for screenshots, brightness, resolution, volume, mute, audio devices, shutdown, restart, suspend, and hibernate.
