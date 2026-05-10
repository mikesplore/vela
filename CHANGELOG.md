# Changelog

## Unreleased

- Phase 1: initialized project skeleton with FastAPI app, config loading from `config.yaml`, JWT authentication, request logging middleware, IP allowlist middleware, public `/health` and `/` endpoints, and systemd service definition under the Vela brand.
- Added authentication tests for token issuance, invalid credentials, expired tokens, and missing credentials.
