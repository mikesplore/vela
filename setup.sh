#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Vela RemotePC Agent — setup script
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

section() { echo; echo "── $* ──"; }
info()    { echo "  $*"; }
warn()    { echo "  WARNING: $*" >&2; }
die()     { echo "  ERROR: $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------

# prompt_value VAR "Label" ["default"]
# Reads into $VAR. If $VAR is already set in the environment, that becomes
# the default. Accepts empty input only when no default exists.
prompt_value() {
  local var_name="$1"
  local label="$2"
  local default="${3:-${!var_name:-}}"
  local answer

  if [[ -n "$default" ]]; then
    read -rp "  $label [$default]: " answer
    printf -v "$var_name" '%s' "${answer:-$default}"
  else
    read -rp "  $label: " answer
    printf -v "$var_name" '%s' "$answer"
  fi
}

# prompt_required VAR "Label" ["default"]  — loops until non-empty
prompt_required() {
  local var_name="$1"
  local label="$2"
  local default="${3:-${!var_name:-}}"

  while true; do
    prompt_value "$var_name" "$label" "$default"
    [[ -n "${!var_name}" ]] && return
    warn "$label is required."
  done
}

# prompt_secret VAR "Label"  — silent input, loops until non-empty.
# Skips if $VAR is already set (env pre-seed).
prompt_secret() {
  local var_name="$1"
  local label="$2"
  local answer

  if [[ -n "${!var_name:-}" ]]; then
    return
  fi

  while true; do
    read -rsp "  $label: " answer; echo
    [[ -n "$answer" ]] && break
    warn "$label is required."
  done
  printf -v "$var_name" '%s' "$answer"
}

# confirm_secret VAL  — prompts for confirmation, loops on mismatch
confirm_secret() {
  local expected="$1"
  local confirm

  while true; do
    read -rsp "  Confirm password: " confirm; echo
    [[ "$confirm" == "$expected" ]] && return
    warn "Passwords do not match. Try again."
  done
}

# ---------------------------------------------------------------------------
# Collect configuration
# ---------------------------------------------------------------------------

section "Vela RemotePC Agent setup"
info "Installing to: $ROOT_DIR"
info "Existing $ENV_FILE will be overwritten."

section "Local service credentials"

DEFAULT_USERNAME="${USERNAME:-${LOCAL_SERVICE_USERNAME:-$(id -un)}}"
prompt_required USERNAME "Username" "$DEFAULT_USERNAME"

PASSWORD="${PASSWORD:-${LOCAL_SERVICE_PASSWORD:-}}"
if [[ -z "$PASSWORD" ]]; then
  prompt_secret PASSWORD "Password"
  confirm_secret "$PASSWORD"
fi
LOCAL_SERVICE_USERNAME="$USERNAME"
LOCAL_SERVICE_PASSWORD="$PASSWORD"

section "VPS relay"

VPS_URL="${VPS_URL:-${RELAY_URL:-}}"
prompt_required VPS_URL "Relay URL (include http:// or https://)"

DEFAULT_AGENT_ID="${AGENT_ID:-$(hostname | tr -cs 'A-Za-z0-9_.-' '-')}"
prompt_required AGENT_ID "Agent ID" "$DEFAULT_AGENT_ID"

# AGENT_SECRET is issued by the relay on first registration; users don't set it.
AGENT_SECRET="${AGENT_SECRET:-${SECRET:-}}"

prompt_value PUBLIC_ADDRESS "Public address of this agent (optional, for first registration)"
prompt_value METADATA       "Agent metadata as JSON (optional, e.g. {\"os\":\"linux\"})"

section "Local API server"

SERVER_HOST="${SERVER_HOST:-127.0.0.1}"
SERVER_PORT="${SERVER_PORT:-8765}"
prompt_required SERVER_HOST "Bind host" "$SERVER_HOST"
prompt_required SERVER_PORT "Port"      "$SERVER_PORT"

if [[ "$SERVER_HOST" != "127.0.0.1" && "$SERVER_HOST" != "localhost" && "$SERVER_HOST" != "::1" ]]; then
  die "Refusing to bind the API to '$SERVER_HOST'. Vela's local API must only listen on localhost."
fi

section "Filesystem access"

ALLOWED_BASE_DIRS="${ALLOWED_BASE_DIRS:-$HOME}"
prompt_required ALLOWED_BASE_DIRS "Directories the agent may access (comma-separated)" "$ALLOWED_BASE_DIRS"

if [[ "$ALLOWED_BASE_DIRS" == "/" ]]; then
  local confirm_root
  read -rp "  Allow access to the entire filesystem? Type 'I understand': " confirm_root
  [[ "$confirm_root" == "I understand" ]] || die "Setup cancelled. Choose narrower base directories."
fi

section "Security (optional)"

ASSISTANT_ACTION_PIN="${ASSISTANT_ACTION_PIN:-${VELA_ASSISTANT_ACTION_PIN:-}}"
if [[ -z "$ASSISTANT_ACTION_PIN" ]]; then
  read -rp "  Assistant action PIN for high-risk operations (press Enter to skip): " answer
  ASSISTANT_ACTION_PIN="${answer:-}"
fi

# ---------------------------------------------------------------------------
# Install Python package
# ---------------------------------------------------------------------------

section "Installing Python environment"

if [[ ! -d "$VENV_DIR" ]]; then
  info "Creating virtualenv at $VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip              -q || die "Failed to upgrade pip."
python -m pip install -e "$ROOT_DIR"             -q || die "Failed to install Vela package."
info "Package installed."

# ---------------------------------------------------------------------------
# Register with VPS relay and validate inputs
# ---------------------------------------------------------------------------

section "Connecting to VPS relay"

export USERNAME PASSWORD LOCAL_SERVICE_USERNAME LOCAL_SERVICE_PASSWORD
export VPS_URL AGENT_ID AGENT_SECRET PUBLIC_ADDRESS METADATA
export SERVER_HOST SERVER_PORT ALLOWED_BASE_DIRS ASSISTANT_ACTION_PIN
export CONFIG_FILE ENV_FILE
# Fireworks vars are optional; export whatever is already in the environment.
export FIREWORKS_API_KEY="${FIREWORKS_API_KEY:-}"
export VELA_FIREWORKS_API_URL="${VELA_FIREWORKS_API_URL:-}"
export VELA_FIREWORKS_MODEL="${VELA_FIREWORKS_MODEL:-}"

# Use a tempfile to pass AGENT_SECRET / AGENT_ID back from the Python subprocess.
AGENT_SECRET_FILE="$(mktemp)"
export AGENT_SECRET_FILE
trap 'rm -f "$AGENT_SECRET_FILE"' EXIT

python - <<'PY'
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

# --- Validate inputs -------------------------------------------------------

vps_url = os.environ["VPS_URL"].strip()
parsed = urlparse(vps_url)
if parsed.scheme not in {"http", "https"} or not parsed.netloc:
    sys.exit("VPS relay URL must include http:// or https:// and a hostname.")

port = int(os.environ["SERVER_PORT"])
if not 1 <= port <= 65535:
    sys.exit("Local API port must be between 1 and 65535.")

for entry in os.environ["ALLOWED_BASE_DIRS"].split(","):
    path = Path(entry.strip()).expanduser()
    if not path.is_absolute():
        sys.exit(f"Allowed base directory must be an absolute path: {entry!r}")

# --- Register with VPS -----------------------------------------------------

agent_secret = os.environ.get("AGENT_SECRET", "").strip()
agent_id = os.environ["AGENT_ID"].strip()

url = f"{vps_url.rstrip('/')}/register"
payload = {"agent_id": agent_id, "public_address": "http://127.0.0.1:0"}
headers = {"X-API-Key": agent_secret} if agent_secret else {}

print(f"  Registering at {url} …")
try:
    resp = requests.post(url, json=payload, headers=headers, timeout=10)
except requests.exceptions.ConnectionError:
    sys.exit(f"Could not connect to {vps_url}. Ensure the VPS is running and reachable.")
except requests.exceptions.Timeout:
    sys.exit(f"Connection to {vps_url} timed out after 10 seconds.")
except requests.exceptions.RequestException as exc:
    sys.exit(f"Request failed: {exc}")

if resp.status_code in {200, 201}:
    data = resp.json()
    print("  Connected to VPS.")
    issued_secret = data.get("secret")
    if issued_secret:
        print(f"  Issued Agent Secret: {issued_secret}")
        print("  IMPORTANT: Save this secret — it authenticates your agent to the relay.")
        agent_secret = issued_secret
    returned = data.get("agent", {})
    if returned.get("agent_id"):
        agent_id = returned["agent_id"]
elif resp.status_code == 401:
    sys.exit("VPS returned 401 Unauthorized. Check your Agent Secret.")
elif resp.status_code == 404:
    sys.exit(f"VPS returned 404 Not Found at {url}. Check your relay URL.")
else:
    sys.exit(f"VPS returned {resp.status_code}: {resp.text}")

# --- Write updated values back to the tempfile (read by bash) --------------

secret_file = os.environ.get("AGENT_SECRET_FILE", "")
if secret_file:
    Path(secret_file).write_text(
        f"AGENT_SECRET={agent_secret}\nAGENT_ID={agent_id}\n",
        encoding="utf-8",
    )
PY

# Absorb any updated AGENT_SECRET / AGENT_ID written by the Python block.
# shellcheck disable=SC1090
source "$AGENT_SECRET_FILE"
export AGENT_SECRET AGENT_ID

# ---------------------------------------------------------------------------
# Generate config.yaml and .env
# ---------------------------------------------------------------------------

section "Writing configuration"

python - <<'PY'
import os
import sys
from pathlib import Path
from secrets import token_urlsafe

import bcrypt
import yaml

# Generate derived secrets
secret_key   = token_urlsafe(32)
pw           = os.environ["PASSWORD"].encode()
password_hash = bcrypt.hashpw(pw, bcrypt.gensalt()).decode()

def csv_list(name: str) -> list[str]:
    return [item.strip() for item in os.environ[name].split(",") if item.strip()]

# ── config.yaml ────────────────────────────────────────────────────────────
config = {
    "host": os.environ["SERVER_HOST"],
    "port": int(os.environ["SERVER_PORT"]),
    "secret_key": secret_key,
    "token_expire_minutes": 1440,
    "allowed_origins": [],
    "allowed_base_dirs": csv_list("ALLOWED_BASE_DIRS"),
    "rate_limit_default": "100/minute",
    "route_rate_limits": {
        "/auth/token": "10/minute",
        "/ping": "60/minute",
    },
    "feature_flags": {
        "display":       True,
        "audio":         True,
        "power":         True,
        "notifications": True,
        "network":       True,
        "filesystem":    True,
        "input_control": True,
        "system_info":   True,
        "monitoring":    True,
        "processes":     True,
        "security":      True,
        "scheduler":     True,
        "maintenance":   True,
        "media":         True,
        "clipboard":     True,
    },
    "username": os.environ["USERNAME"],
    "password_hash": password_hash,
    "log_level": "INFO",
}

if pin := os.environ.get("ASSISTANT_ACTION_PIN", "").strip():
    config["assistant_action_pin"] = pin

Path(os.environ["CONFIG_FILE"]).write_text(
    yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
)
print(f"  config.yaml written to {os.environ['CONFIG_FILE']}")

# ── .env ───────────────────────────────────────────────────────────────────
local_service_url = f"http://127.0.0.1:{os.environ['SERVER_PORT']}"

fw_url   = (os.environ.get("VELA_FIREWORKS_API_URL") or
            os.environ.get("FIREWORKS_API_URL") or
            "https://api.fireworks.ai/inference/v1")
fw_model = (os.environ.get("VELA_FIREWORKS_MODEL") or
            os.environ.get("FIREWORKS_MODEL") or
            "accounts/fireworks/models/deepseek-v4-flash")

lines = [
    f"USERNAME={os.environ['USERNAME']}",
    f"PASSWORD={os.environ['PASSWORD']}",
    f"LOCAL_SERVICE_USERNAME={os.environ['LOCAL_SERVICE_USERNAME']}",
    f"LOCAL_SERVICE_PASSWORD={os.environ['LOCAL_SERVICE_PASSWORD']}",
    f"LOCAL_SERVICE_URL={local_service_url}",
    f"LOCAL_SERVICE_TOKEN_PATH=/auth/token",
    f"LOCAL_SERVICE_AUTH_TOKEN=",
    f"LOCAL_SERVICE_AUTH_TOKEN_EXPIRES=",
    f"VPS_URL={os.environ['VPS_URL']}",
    f"AGENT_ID={os.environ['AGENT_ID']}",
    f"AGENT_SECRET={os.environ['AGENT_SECRET']}",
    f"ASSISTANT_ACTION_PIN={os.environ.get('ASSISTANT_ACTION_PIN', '')}",
    f"FIREWORKS_API_KEY='paste_your_key_here'",
    f"VELA_ASSISTANT_ENABLE_THINKING='false'",
    f"VELA_FIREWORKS_API_URL={fw_url}",
    f"VELA_FIREWORKS_MODEL={fw_model}",
]

if addr := os.environ.get("PUBLIC_ADDRESS", "").strip():
    lines.append(f"PUBLIC_ADDRESS={addr}")
if meta := os.environ.get("METADATA", "").strip():
    lines.append(f"METADATA={meta}")
if fw_key := os.environ.get("FIREWORKS_API_KEY", "").strip():
    lines.append(f"FIREWORKS_API_KEY={fw_key}")

env_path = Path(os.environ["ENV_FILE"])
env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
env_path.chmod(0o600)
print(f"  .env written to {env_path}")
PY

CONFIG_FILE="$CONFIG_FILE" python -c "
import os; from pathlib import Path
p = Path(os.environ['CONFIG_FILE'])
if not p.exists(): raise SystemExit('config.yaml was not created')
"

[[ -f "$ENV_FILE" ]] || die ".env was not created."

# ---------------------------------------------------------------------------
# Write desktop environment snapshot
# ---------------------------------------------------------------------------

mkdir -p "$SERVICE_DIR" "$(dirname "$DESKTOP_ENV_FILE")"

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

# ---------------------------------------------------------------------------
# Install systemd user services
# ---------------------------------------------------------------------------

section "Installing systemd services"

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

systemctl --user daemon-reload
systemctl --user enable --now "$SERVICE_NAME"
systemctl --user enable --now "$AGENT_SERVICE_NAME"
info "Services enabled and started."

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

section "Setup complete"
info "Config:        $CONFIG_FILE"
info "Environment:   $ENV_FILE"
info "Service:       $SERVICE_PATH"
info "Agent service: $AGENT_SERVICE_PATH"
info "Local API:     http://127.0.0.1:$SERVER_PORT"