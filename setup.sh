#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
CONFIG_FILE="$ROOT_DIR/config.yaml"
SERVICE_NAME="vela.service"
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_PATH="$SERVICE_DIR/$SERVICE_NAME"

echo "Setting up Vela RemotePC Agent in $ROOT_DIR"

if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r "$ROOT_DIR/requirements.txt"

read -rp "Username [admin]: " USERNAME
USERNAME="${USERNAME:-admin}"

read -rsp "Password: " PASSWORD
echo
if [[ -z "$PASSWORD" ]]; then
  echo "Password is required." >&2
  exit 1
fi

SECRET_KEY="$(python - <<'PY'
from secrets import token_urlsafe
print(token_urlsafe(32))
PY
)"

PASSWORD_HASH="$(VELA_PASSWORD="$PASSWORD" python - <<'PY'
import bcrypt, os
pw = os.environ['VELA_PASSWORD'].encode('utf-8')
hash = bcrypt.hashpw(pw, bcrypt.gensalt()).decode('utf-8')
print(hash)
PY
)"

cat > "$CONFIG_FILE" <<EOF
host: 0.0.0.0
port: 8765
secret_key: $SECRET_KEY
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
username: $USERNAME
password_hash: "$PASSWORD_HASH"
log_level: INFO
EOF

mkdir -p "$SERVICE_DIR"
cat > "$SERVICE_PATH" <<EOF
[Unit]
Description=Vela RemotePC Agent
After=network.target

[Service]
Type=simple
WorkingDirectory=$ROOT_DIR
ExecStart=$VENV_DIR/bin/python $ROOT_DIR/main.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

echo "Reloading systemd user daemon..."
systemctl --user daemon-reload
systemctl --user enable --now "$SERVICE_NAME"

echo "Setup complete."
echo "Config path: $CONFIG_FILE"
echo "Service: $SERVICE_PATH"

echo "Local access URL: http://$(python -c 'import socket; print([ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if not ip.startswith("127.")][0] if True else "127.0.0.1")'):8765"
