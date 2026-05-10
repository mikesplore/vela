#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
CONFIG_FILE="$ROOT_DIR/config.yaml"
ENV_FILE="$ROOT_DIR/.env"
SERVICE_NAME="vela.service"
AGENT_SERVICE_NAME="vela-agent.service"
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_PATH="$SERVICE_DIR/$SERVICE_NAME"
AGENT_SERVICE_PATH="$SERVICE_DIR/$AGENT_SERVICE_NAME"

echo "Setting up Vela RemotePC Agent in $ROOT_DIR"

if [[ -f "$ENV_FILE" ]]; then
  set -o allexport
  source "$ENV_FILE"
  set +o allexport
  echo "Loaded environment values from $ENV_FILE"
fi

if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r "$ROOT_DIR/requirements.txt"

USERNAME="${USERNAME:-admin}"
PASSWORD="${PASSWORD:-}"
LOCAL_SERVICE_USERNAME="${LOCAL_SERVICE_USERNAME:-$USERNAME}"
LOCAL_SERVICE_PASSWORD="${LOCAL_SERVICE_PASSWORD:-$PASSWORD}"
PASSWORD="${PASSWORD:-$LOCAL_SERVICE_PASSWORD}"

if [[ -z "$PASSWORD" ]]; then
  read -rp "Username [admin]: " USERNAME
  USERNAME="${USERNAME:-admin}"

  read -rsp "Password: " PASSWORD
  echo
  if [[ -z "$PASSWORD" ]]; then
    echo "Password is required." >&2
    exit 1
  fi
  LOCAL_SERVICE_USERNAME="${LOCAL_SERVICE_USERNAME:-$USERNAME}"
  LOCAL_SERVICE_PASSWORD="${LOCAL_SERVICE_PASSWORD:-$PASSWORD}"
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
cat > "$ENV_FILE" <<EOF
USERNAME=$USERNAME
PASSWORD=$PASSWORD
LOCAL_SERVICE_USERNAME=$LOCAL_SERVICE_USERNAME
LOCAL_SERVICE_PASSWORD=$LOCAL_SERVICE_PASSWORD
LOCAL_SERVICE_URL=http://localhost:8765
LOCAL_SERVICE_TOKEN_PATH=/auth/token
EOF
chmod 600 "$ENV_FILE"

echo "Generated environment file at $ENV_FILE"

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

cat > "$AGENT_SERVICE_PATH" <<EOF
[Unit]
Description=Vela RemotePC Agent Tunnel
After=network.target

[Service]
Type=simple
WorkingDirectory=$ROOT_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$VENV_DIR/bin/python $ROOT_DIR/agent.py
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
systemctl --user enable --now "$AGENT_SERVICE_NAME"

echo "Setup complete."
echo "Config path: $CONFIG_FILE"
echo "Service: $SERVICE_PATH"
echo "Agent service: $AGENT_SERVICE_PATH"

echo "Local access URL: http://$(python -c 'import socket; print([ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if not ip.startswith("127.")][0] if True else "127.0.0.1")'):8765"
