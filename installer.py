import argparse
import getpass
import os
from pathlib import Path
from secrets import token_urlsafe

import bcrypt


DEFAULT_CONFIG_DIR = Path.home() / ".config" / "vela"
SYSTEMD_USER_DIR = Path.home() / ".config" / "systemd" / "user"
DEFAULT_SERVICE_USERNAME = os.getenv("USERNAME", "admin")


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _config_yaml(username: str, password_hash: str, secret_key: str) -> str:
    return f"""host: 0.0.0.0
port: 8765
secret_key: {secret_key}
token_expire_minutes: 1440
allowed_origins: []
allowed_ips: []
allowed_base_dirs: []
rate_limit_default: 100/minute
route_rate_limits:
  /auth/token: 10/minute
  /ping: 60/minute
feature_flags:
  display: true
  audio: true
  power: true
  notifications: true
  network: true
  filesystem: true
  input_control: true
  system_info: true
  monitoring: true
  processes: true
  security: true
  scheduler: true
  maintenance: true
  media: true
  clipboard: true
username: {username}
password_hash: "{password_hash}"
log_level: INFO
"""


def _env_file(username: str, password: str) -> str:
    return f"""USERNAME={username}
PASSWORD={password}
LOCAL_SERVICE_USERNAME={username}
LOCAL_SERVICE_PASSWORD={password}
LOCAL_SERVICE_URL=http://localhost:8765
LOCAL_SERVICE_TOKEN_PATH=/auth/token
"""


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Initialize a packaged Vela install")
    parser.add_argument("--config-dir", default=str(DEFAULT_CONFIG_DIR), help="Directory to store config.yaml and .env")
    parser.add_argument("--username", default=DEFAULT_SERVICE_USERNAME, help="Login username for the local service")
    parser.add_argument("--password", help="Login password for the local service")
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

    secret_key = token_urlsafe(32)
    password_hash = _hash_password(service_password)

    config_yaml_path = config_dir / "config.yaml"
    env_file_path = config_dir / ".env"

    _write_text(config_yaml_path, _config_yaml(service_username, password_hash, secret_key))
    _write_text(env_file_path, _env_file(service_username, service_password))
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