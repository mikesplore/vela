import argparse
import getpass
import os
import socket
from pathlib import Path
from secrets import token_urlsafe
from urllib.parse import urlparse

import bcrypt
import requests
import yaml


DEFAULT_CONFIG_DIR = Path.home() / ".config" / "vela"
SYSTEMD_USER_DIR = Path.home() / ".config" / "systemd" / "user"
DEFAULT_SERVICE_USERNAME = os.getenv("USERNAME", "admin")


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _csv_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _config_yaml(
    username: str,
    password_hash: str,
    secret_key: str,
    host: str,
    port: int,
    allowed_base_dirs: list[str],
) -> str:
    config = {
        "host": host,
        "port": port,
        "secret_key": secret_key,
        "token_expire_minutes": 1440,
        "allowed_origins": [],
        "allowed_base_dirs": allowed_base_dirs,
        "rate_limit_default": "100/minute",
        "route_rate_limits": {
            "/auth/token": "10/minute",
            "/ping": "60/minute",
        },
        "feature_flags": {
            "display": True,
            "audio": True,
            "power": True,
            "notifications": True,
            "network": True,
            "filesystem": True,
            "input_control": True,
            "system_info": True,
            "monitoring": True,
            "processes": True,
            "security": True,
            "scheduler": True,
            "maintenance": True,
            "media": True,
            "clipboard": True,
        },
        "username": username,
        "password_hash": password_hash,
        "log_level": "INFO",
    }
    return yaml.safe_dump(config, sort_keys=False)


def _env_file(username: str, password: str, port: int, vps_url: str, agent_id: str, agent_secret: str = "") -> str:
    values = {
        "USERNAME": username,
        "PASSWORD": password,
        "LOCAL_SERVICE_USERNAME": username,
        "LOCAL_SERVICE_PASSWORD": password,
        "LOCAL_SERVICE_URL": f"http://127.0.0.1:{port}",
        "LOCAL_SERVICE_TOKEN_PATH": "/auth/token",
        "LOCAL_SERVICE_AUTH_TOKEN": "",
        "LOCAL_SERVICE_AUTH_TOKEN_EXPIRES": "",
        "VPS_URL": vps_url,
        "AGENT_ID": agent_id,
        "AGENT_SECRET": agent_secret,
    }
    return "".join(f"{key}={value!r}\n" for key, value in values.items())


def _service_file(
    service_name: str,
    exec_start: str,
    environment_file: Path,
    workdir: Path,
    extra_env: list[str] | None = None,
) -> str:
    env_lines = "\n".join(f"Environment={line}" for line in (extra_env or []))
    if env_lines:
        env_lines += "\n"
    return f"""[Unit]
Description={service_name}
After=network.target

[Service]
Type=simple
WorkingDirectory={workdir}
EnvironmentFile={environment_file}
{env_lines}ExecStart={exec_start}
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
"""


def _run_systemctl(*args: str) -> None:
    os.system("systemctl --user " + " ".join(args))


def _test_vps_connectivity(vps_url: str, agent_id: str, agent_secret: str = "") -> None:
    """Test connectivity to the VPS using the new /register endpoint."""
    print(f"Testing connectivity to VPS at {vps_url}...")
    try:
        url = f"{vps_url.rstrip('/')}/register"
        payload = {"agent_id": agent_id}
        headers = {}

        if agent_secret:
            # Authenticated test (re-registration)
            payload["public_address"] = "http://127.0.0.1:0"
            headers["X-API-Key"] = agent_secret
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
        else:
            # First-time registration test
            payload["public_address"] = "http://127.0.0.1:0"
            resp = requests.post(url, json=payload, timeout=10)

        if resp.status_code == 200:
            data = resp.json()
            print("Successfully connected to VPS.")
            issued_secret = data.get("secret")
            if issued_secret:
                print(f"Issued Agent Secret: {issued_secret}")
                print("IMPORTANT: Save this secret. It authenticates your agent to the VPS relay.")
                print("You'll pass it as X-API-Key header in client requests to this agent,")
                print(f"e.g.: curl -H 'X-API-Key: {issued_secret}' http://<vps-url>/...")
            else:
                print("VPS acknowledged registration.")
        elif resp.status_code == 401:
            raise SystemExit("Failed to verify credentials: VPS returned 401 Unauthorized.")
        elif resp.status_code == 404:
            raise SystemExit(f"Failed to reach registration endpoint: VPS returned 404 Not Found at {url}.")
        else:
            raise SystemExit(f"Failed to connect to VPS: Status {resp.status_code} - {resp.text}")
    except requests.exceptions.RequestException as e:
        raise SystemExit(f"Failed to connect to VPS at {vps_url}: {e}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Initialize a packaged Vela install")
    parser.add_argument("--config-dir", default=str(DEFAULT_CONFIG_DIR), help="Directory to store config.yaml and .env")
    parser.add_argument("--username", default=DEFAULT_SERVICE_USERNAME, help="Login username for the local service")
    parser.add_argument("--password", help="Login password for the local service")
    parser.add_argument("--vps-url", help="VPS relay URL, including http:// or https://")
    parser.add_argument("--agent-id", default=f"{getpass.getuser()}-{socket.gethostname()}", help="Agent ID registered with the VPS relay")
    parser.add_argument("--agent-secret", help="Agent registration secret from the VPS relay (not needed for first-time registration)")
    parser.add_argument("--host", default="127.0.0.1", help="Local API bind host; must be localhost")
    parser.add_argument("--port", type=int, default=8765, help="Local API port")
    parser.add_argument("--allowed-base-dirs", default=str(Path.home()), help="Comma-separated filesystem base directories")
    parser.add_argument("--no-systemd", action="store_true", help="Skip systemd unit installation")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    config_dir = Path(args.config_dir).expanduser().resolve()
    service_username = args.username or DEFAULT_SERVICE_USERNAME
    service_password = args.password or getpass.getpass("Password: ")
    if not service_password:
        raise SystemExit("Password is required.")
    vps_url = args.vps_url or input("VPS relay URL, including http:// or https://: ").strip()
    parsed_vps = urlparse(vps_url)
    if parsed_vps.scheme not in {"http", "https"} or not parsed_vps.netloc:
        raise SystemExit("VPS relay URL must include http:// or https:// and a host.")

    agent_secret = args.agent_secret or ""
    if not agent_secret:
        # Ask whether they have an existing secret
        answer = input("Do you have an existing agent secret from a previous registration? (y/N): ").strip().lower()
        if answer in ("y", "yes"):
            agent_secret = getpass.getpass("Agent registration secret from the VPS relay: ")
            if not agent_secret:
                raise SystemExit("Agent registration secret is required.")
        else:
            print("No secret provided — will perform first-time registration with the VPS.")

    _test_vps_connectivity(vps_url, args.agent_id, agent_secret)

    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("The local API must only bind to localhost.")
    if not 1 <= args.port <= 65535:
        raise SystemExit("Port must be between 1 and 65535.")
    allowed_base_dirs = _csv_list(args.allowed_base_dirs)
    if not allowed_base_dirs:
        raise SystemExit("At least one allowed base directory is required.")
    if allowed_base_dirs == ["/"]:
        confirm = input("Allow filesystem access to the entire host? Type 'I understand': ")
        if confirm != "I understand":
            raise SystemExit("Choose narrower allowed base directories.")
    for value in allowed_base_dirs:
        if not Path(value).expanduser().is_absolute():
            raise SystemExit(f"Allowed base directory must be absolute: {value}")

    secret_key = token_urlsafe(32)
    password_hash = _hash_password(service_password)

    config_yaml_path = config_dir / "config.yaml"
    env_file_path = config_dir / ".env"

    _write_text(
        config_yaml_path,
        _config_yaml(
            service_username,
            password_hash,
            secret_key,
            args.host,
            args.port,
            allowed_base_dirs,
        ),
    )
    _write_text(env_file_path, _env_file(service_username, service_password, args.port, vps_url, args.agent_id, agent_secret))
    env_file_path.chmod(0o600)

    print(f"Wrote config to {config_yaml_path}")
    print(f"Wrote env file to {env_file_path}")

    if args.no_systemd:
        return

    vela_exec = Path(os.popen("command -v vela").read().strip() or "vela").resolve()
    vela_agent_exec = Path(os.popen("command -v vela-agent").read().strip() or "vela-agent").resolve()

    SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)
    _write_text(
        SYSTEMD_USER_DIR / "vela.service",
        _service_file(
            "Vela API",
            str(vela_exec),
            env_file_path,
            config_dir,
            ["START_AGENT=false", f"REMOTEAGENT_CONFIG_PATH={config_yaml_path}"],
        ),
    )
    _write_text(
        SYSTEMD_USER_DIR / "vela-agent.service",
        _service_file(
            "Vela Agent",
            str(vela_agent_exec),
            env_file_path,
            config_dir,
            [f"REMOTEAGENT_CONFIG_PATH={config_yaml_path}"],
        ),
    )

    _run_systemctl("daemon-reload")
    _run_systemctl("enable", "--now", "vela.service")
    _run_systemctl("enable", "--now", "vela-agent.service")

    print(f"Installed systemd units in {SYSTEMD_USER_DIR}")


if __name__ == "__main__":
    main()