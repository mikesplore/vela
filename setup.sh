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
DESKTOP_ENV_FILE="$HOME/.config/vela/desktop.env"

echo "Setting up Vela RemotePC Agent in $ROOT_DIR"

if [[ -f "$ENV_FILE" ]]; then
  set -o allexport
  source "$ENV_FILE"
  set +o allexport
  echo "Loaded environment values from $ENV_FILE"
fi

prompt_value() {
  local var_name="$1"
  local prompt="$2"
  local default_value="${3:-}"
  local current_value="${!var_name:-}"
  local answer=""

  if [[ -n "$current_value" ]]; then
    default_value="$current_value"
  fi

  if [[ -n "$default_value" ]]; then
    read -rp "$prompt [$default_value]: " answer
    printf -v "$var_name" '%s' "${answer:-$default_value}"
  else
    read -rp "$prompt: " answer
    printf -v "$var_name" '%s' "$answer"
  fi
}

prompt_required() {
  local var_name="$1"
  local prompt="$2"
  local default_value="${3:-}"

  while true; do
    prompt_value "$var_name" "$prompt" "$default_value"
    if [[ -n "${!var_name}" ]]; then
      break
    fi
    echo "$prompt is required." >&2
  done
}

prompt_secret_required() {
  local var_name="$1"
  local prompt="$2"
  local current_value="${!var_name:-}"
  local answer=""

  if [[ -n "$current_value" ]]; then
    return
  fi

  while true; do
    read -rsp "$prompt: " answer
    echo
    if [[ -n "$answer" ]]; then
      printf -v "$var_name" '%s' "$answer"
      break
    fi
    echo "$prompt is required." >&2
  done
}

confirm_secret() {
  local first="$1"
  local second=""

  read -rsp "Confirm password: " second
  echo
  if [[ "$first" != "$second" ]]; then
    echo "Passwords do not match." >&2
    exit 1
  fi
}

if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip > /dev/null 2>&1 || { echo "Failed to upgrade pip"; exit 1; }
python -m pip install -e "$ROOT_DIR" > /dev/null 2>&1 || { echo "Failed to install Vela package"; exit 1; }

DEFAULT_USERNAME="${USERNAME:-${LOCAL_SERVICE_USERNAME:-$(id -un)}}"
prompt_required USERNAME "Local service username" "$DEFAULT_USERNAME"

PASSWORD="${PASSWORD:-${LOCAL_SERVICE_PASSWORD:-}}"
if [[ -z "$PASSWORD" ]]; then
  prompt_secret_required PASSWORD "Local service password"
  confirm_secret "$PASSWORD"
fi
LOCAL_SERVICE_USERNAME="$USERNAME"
LOCAL_SERVICE_PASSWORD="$PASSWORD"

VPS_URL="${VPS_URL:-${RELAY_URL:-}}"
prompt_required VPS_URL "VPS relay URL, including http:// or https://"

DEFAULT_AGENT_ID="${AGENT_ID:-$(hostname | tr -cs 'A-Za-z0-9_.-' '-')}"
prompt_required AGENT_ID "Agent ID registered with the VPS relay" "$DEFAULT_AGENT_ID"

# AGENT_SECRET is now optional — the VPS issues one on first registration
AGENT_SECRET="${AGENT_SECRET:-${SECRET:-}}"
if [[ -z "$AGENT_SECRET" ]]; then
  read -rp "Do you have an existing agent secret from a previous registration? (y/N): " has_secret
  if [[ "$has_secret" == "y" || "$has_secret" == "Y" ]]; then
    prompt_secret_required AGENT_SECRET "Agent registration secret from the VPS relay"
  else
    echo "No existing secret — will perform first-time registration with the VPS."
  fi
fi

# Optional: Public address and metadata for first-time agent registration
PUBLIC_ADDRESS="${PUBLIC_ADDRESS:-}"
read -rp "Public address of this agent (optional, for first registration): " answer
if [[ -n "$answer" ]]; then
  PUBLIC_ADDRESS="$answer"
fi

METADATA="${METADATA:-}"
read -rp "Agent metadata as JSON string (optional, e.g. {\"os\": \"linux\"}): " answer
if [[ -n "$answer" ]]; then
  METADATA="$answer"
fi

SERVER_HOST="${SERVER_HOST:-127.0.0.1}"
SERVER_PORT="${SERVER_PORT:-8765}"
prompt_required SERVER_HOST "Local API bind host" "$SERVER_HOST"
prompt_required SERVER_PORT "Local API port" "$SERVER_PORT"

if [[ "$SERVER_HOST" != "127.0.0.1" && "$SERVER_HOST" != "localhost" && "$SERVER_HOST" != "::1" ]]; then
  echo "Refusing to bind the API to '$SERVER_HOST'. Vela's local API must only listen on localhost." >&2
  exit 1
fi

ALLOWED_BASE_DIRS="${ALLOWED_BASE_DIRS:-$HOME}"
prompt_required ALLOWED_BASE_DIRS "Filesystem base directories the agent may access, comma-separated" "$ALLOWED_BASE_DIRS"
if [[ "$ALLOWED_BASE_DIRS" == "/" ]]; then
  read -rp "Allow filesystem access to the entire host? Type 'I understand': " CONFIRM_ROOT_FS
  if [[ "$CONFIRM_ROOT_FS" != "I understand" ]]; then
    echo "Setup cancelled. Choose narrower allowed base directories." >&2
    exit 1
  fi
fi

ASSISTANT_ACTION_PIN="${ASSISTANT_ACTION_PIN:-${VELA_ASSISTANT_ACTION_PIN:-}}"
read -rp "Assistant action PIN for high-risk actions (shutdown, delete, kill process, etc.) - press Enter to skip: " answer
if [[ -n "$answer" ]]; then
  ASSISTANT_ACTION_PIN="$answer"
fi

export USERNAME PASSWORD LOCAL_SERVICE_USERNAME LOCAL_SERVICE_PASSWORD
export VPS_URL AGENT_ID AGENT_SECRET PUBLIC_ADDRESS METADATA SERVER_HOST SERVER_PORT ALLOWED_BASE_DIRS ASSISTANT_ACTION_PIN

python - <<'PY'
import os
from pathlib import Path
from urllib.parse import urlparse
import requests

vps_url = os.environ["VPS_URL"].strip()
parsed = urlparse(vps_url)
if parsed.scheme not in {"http", "https"} or not parsed.netloc:
    raise SystemExit("VPS relay URL must include http:// or https:// and a host.")

agent_secret = os.environ.get("AGENT_SECRET", "").strip()
agent_id = os.environ.get("AGENT_ID", "").strip()

print(f"Testing connectivity to VPS at {vps_url}/register...")
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
            # Export it so it gets saved to .env
            os.environ["AGENT_SECRET"] = issued_secret
    elif resp.status_code == 401:
        raise SystemExit("Failed to verify credentials: VPS returned 401 Unauthorized. Check your Agent Secret.")
    elif resp.status_code == 404:
        raise SystemExit(f"Failed to reach registration endpoint: VPS returned 404 Not Found at {url}.")
    else:
        raise SystemExit(f"Failed to connect to VPS: Status {resp.status_code} - {resp.text}")
except requests.exceptions.ConnectionError:
    raise SystemExit(f"Could not connect to {vps_url}. Ensure the VPS is running and reachable.")
except requests.exceptions.Timeout:
    raise SystemExit(f"Connection to {vps_url} timed out after 10 seconds.")
except requests.exceptions.RequestException as e:
    raise SystemExit(f"Failed to connect to VPS at {vps_url}: {e}")

port = int(os.environ["SERVER_PORT"])
if not 1 <= port <= 65535:
    raise SystemExit("Local API port must be between 1 and 65535.")

for value in os.environ["ALLOWED_BASE_DIRS"].split(","):
    path = Path(value.strip()).expanduser()
    if not path.is_absolute():
        raise SystemExit(f"Allowed base directory must be absolute: {value}")
PY

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

VELA_CONFIG_FILE="$CONFIG_FILE" \
VELA_SECRET_KEY_VALUE="$SECRET_KEY" \
VELA_PASSWORD_HASH_VALUE="$PASSWORD_HASH" \
python - <<'PY'
import os
from pathlib import Path

import yaml

def csv_list(name: str) -> list[str]:
    return [item.strip() for item in os.environ[name].split(",") if item.strip()]

config = {
    "host": os.environ["SERVER_HOST"],
    "port": int(os.environ["SERVER_PORT"]),
    "secret_key": os.environ["VELA_SECRET_KEY_VALUE"],
    "token_expire_minutes": 1440,
    "allowed_origins": [],
    "allowed_base_dirs": csv_list("ALLOWED_BASE_DIRS"),
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
    "username": os.environ["USERNAME"],
    "password_hash": os.environ["VELA_PASSWORD_HASH_VALUE"],
    "log_level": "INFO",
}

assistant_action_pin = os.environ.get("ASSISTANT_ACTION_PIN", "").strip()
if assistant_action_pin:
    config["assistant_action_pin"] = assistant_action_pin

Path(os.environ["VELA_CONFIG_FILE"]).write_text(
    yaml.safe_dump(config, sort_keys=False),
    encoding="utf-8",
)
PY

mkdir -p "$SERVICE_DIR"
mkdir -p "$(dirname "$DESKTOP_ENV_FILE")"
cat > "$DESKTOP_ENV_FILE" <<EOF
DISPLAY=${DISPLAY:-}
WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-}
XAUTHORITY=${XAUTHORITY:-}
DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS:-}
XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-}
XDG_SESSION_TYPE=${XDG_SESSION_TYPE:-}
XDG_CURRENT_DESKTOP=${XDG_CURRENT_DESKTOP:-}
DESKTOP_SESSION=${DESKTOP_SESSION:-}
EOF
chmod 600 "$DESKTOP_ENV_FILE"

LOCAL_SERVICE_URL="http://127.0.0.1:$SERVER_PORT"
export LOCAL_SERVICE_URL
ENV_FILE="$ENV_FILE" python - <<'PY'
import os
from dotenv import set_key

env_file = os.environ["ENV_FILE"]
open(env_file, "a", encoding="utf-8").close()
for key in (
    "USERNAME",
    "PASSWORD",
    "LOCAL_SERVICE_USERNAME",
    "LOCAL_SERVICE_PASSWORD",
    "LOCAL_SERVICE_URL",
    "VPS_URL",
    "AGENT_ID",
    "AGENT_SECRET",
    "ASSISTANT_ACTION_PIN",
):
    set_key(env_file, key, os.environ[key])

# Set optional registration fields if provided
public_address = os.environ.get("PUBLIC_ADDRESS", "").strip()
if public_address:
    set_key(env_file, "PUBLIC_ADDRESS", public_address)

metadata = os.environ.get("METADATA", "").strip()
if metadata:
    set_key(env_file, "METADATA", metadata)

set_key(env_file, "LOCAL_SERVICE_TOKEN_PATH", "/auth/token")
set_key(env_file, "LOCAL_SERVICE_AUTH_TOKEN", "")
set_key(env_file, "LOCAL_SERVICE_AUTH_TOKEN_EXPIRES", "")
PY
chmod 600 "$ENV_FILE"

echo "Generated environment file at $ENV_FILE"

cat > "$SERVICE_PATH" <<EOF
[Unit]
Description=Vela RemotePC Agent
After=network.target

[Service]
Type=simple
WorkingDirectory=$ROOT_DIR
Environment=START_AGENT=false
EnvironmentFile=$DESKTOP_ENV_FILE
ExecStart=$VENV_DIR/bin/vela
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
ExecStart=$VENV_DIR/bin/vela-agent
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

echo "Local access URL: http://127.0.0.1:$SERVER_PORT"