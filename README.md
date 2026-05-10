# Vela RemotePC Agent

A secure FastAPI-based remote control agent for Linux PCs. Vela exposes system, media, clipboard, filesystem, network, scheduler, and maintenance APIs behind JWT authentication.

## Prerequisites

- Python 3.13+
- Linux desktop environment with `xrandr`, `playerctl`, `xdotool`, `nmcli`, `bluetoothctl`, `systemctl`, and `journalctl` available where applicable
- `python3-venv` and `python3-pip`
- A user-level systemd session for service deployment

## Installation

1. Clone the repo:
```bash
git clone https://your-repo-url.git ~/Development/vela
cd ~/Development/vela
```
2. Run the setup script:
```bash
./setup.sh
```
3. The script will install dependencies, generate `config.yaml`, hash your password, and optionally install the systemd user service.

## Configuration

`config.yaml` includes:

- `host` / `port`
- `secret_key`
- `username` / `password_hash`
- `allowed_origins`
- `allowed_ips`
- `allowed_base_dirs`
- `rate_limit_default`
- `route_rate_limits`
- `feature_flags`

### Filesystem security

Set `allowed_base_dirs` to the directories the agent may access. If empty, all paths are permitted.

### Rate limiting

- `rate_limit_default`: global default limit
- `route_rate_limits`: map endpoint paths to custom limits

Example:
```yaml
rate_limit_default: 100/minute
route_rate_limits:
  /auth/token: 10/minute
  /ping: 60/minute
```

## Running

Start locally:
```bash
source .venv/bin/activate
python main.py
```

OpenAPI docs are available at `http://<host>:<port>/docs`.

## Systemd service

The service file can be installed for the current user via `./setup.sh`. The service will run the agent on login and restart on failure.

## Connecting from a phone

Use the local LAN IP shown by `ip a` or `hostname -I`. If you run behind Tailscale or another tunnel, use the provided private address and open port.

## Security recommendations

- Use a strong `secret_key`
- Do not expose the API directly to the public internet
- Use an allowlist in `allowed_ips` when possible
- Use `allowed_base_dirs` to restrict filesystem access

## Adding a new feature module

1. Add a router file under `routers/`
2. Export its router in `routers/__init__.py`
3. Add the router to `all_routers`
4. Add `feature_flags` in `config.yaml`
5. Add tests under `tests/`
6. Update `CHANGELOG.md`
