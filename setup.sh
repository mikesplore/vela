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
# System dependency checks
# ---------------------------------------------------------------------------

detect_pkg_manager() {
  if command -v apt-get >/dev/null 2>&1; then
    echo "apt"
    return
  fi
  if command -v dnf >/dev/null 2>&1; then
    echo "dnf"
    return
  fi
  if command -v pacman >/dev/null 2>&1; then
    echo "pacman"
    return
  fi
  echo "unknown"
}

check_and_offer_system_dependencies() {
  local pkg_manager="$1"
  local -a groups=(
    "Filesystem|Open files and paths from API calls.|xdg-open|xdg-utils|xdg-utils|xdg-utils"
    "Audio|Adjust volume/output and play sounds.|amixer pactl|alsa-utils pulseaudio-utils|alsa-utils pulseaudio-utils|alsa-utils pulseaudio-utils"
    "Display/Screenshot|Manage display state and capture screenshots.|xrandr flameshot xset ffmpeg busctl brightnessctl gsettings|x11-xserver-utils flameshot ffmpeg libglib2.0-bin brightnessctl systemd|xorg-xrandr flameshot xorg-xset ffmpeg glib2 brightnessctl systemd|xorg-xrandr flameshot xorg-xset ffmpeg glib2 brightnessctl systemd"
    "Input Control|Mouse/keyboard actions and window introspection.|xdotool xprop xwininfo|xdotool x11-utils|xdotool xorg-xprop xorg-xwininfo|xdotool xorg-xprop xorg-xwininfo"
    "Media|Control media playback sessions.|playerctl|playerctl|playerctl|playerctl"
    "Network|Inspect/manage network, bluetooth, and connectivity tests.|nmcli bluetoothctl rfkill ping|network-manager bluez util-linux iputils-ping|NetworkManager bluez util-linux iputils|networkmanager bluez util-linux iputils"
    "Notifications|Send desktop notifications.|notify-send|libnotify-bin|libnotify|libnotify"
    "Power|Power actions and profile controls.|systemctl powerprofilesctl|systemd power-profiles-daemon|systemd power-profiles-daemon|systemd power-profiles-daemon"
    "Security|Lock/session and webcam security operations.|loginctl modprobe pactl pkill who ffmpeg|systemd kmod pulseaudio-utils procps util-linux coreutils ffmpeg|systemd kmod pulseaudio-utils procps-ng util-linux coreutils ffmpeg|systemd kmod pulseaudio-utils procps-ng util-linux coreutils ffmpeg"
    "System Info|Read hardware/system inventory.|lspci lsusb dmidecode xrandr|pciutils usbutils dmidecode x11-xserver-utils|pciutils usbutils dmidecode xorg-xrandr|pciutils usbutils dmidecode xorg-xrandr"
    "Maintenance|Inspect service logs/time state.|journalctl systemctl timedatectl|systemd|systemd|systemd"
  )
  local -a missing_rows=()
  local row feature description commands missing

  section "Checking system dependencies"
  info "Vela checks runtime tools by feature and can install missing packages."

  for row in "${groups[@]}"; do
    IFS='|' read -r feature description commands _ <<< "$row"
    missing=()
    for cmd in $commands; do
      if ! command -v "$cmd" >/dev/null 2>&1; then
        missing+=("$cmd")
      fi
    done
    if ((${#missing[@]})); then
      missing_rows+=("$row|${missing[*]}")
    fi
  done

  if ((${#missing_rows[@]} == 0)); then
    info "All checked runtime tools are already available."
    return
  fi

  echo
  info "Missing tools detected:"
  for row in "${missing_rows[@]}"; do
    IFS='|' read -r feature description _ _ _ _ missing <<< "$row"
    echo "  - $feature"
    echo "    What it does: $description"
    echo "    Missing commands: $missing"
  done
  echo

  read -rp "  Install missing packages now? [y/N]: " install_missing
  if [[ ! "${install_missing:-N}" =~ ^[Yy]([Ee][Ss])?$ ]]; then
    info "Skipping package install. Missing features may fail until tools are installed."
    return
  fi

  if [[ "$pkg_manager" == "unknown" ]]; then
    warn "No supported package manager detected (apt, dnf, pacman). Install tools manually."
    return
  fi

  local -A pkg_set=()

  for row in "${missing_rows[@]}"; do
    IFS='|' read -r _ _ _ apt_pkgs dnf_pkgs pacman_pkgs _ <<< "$row"
    local pkgs
    case "$pkg_manager" in
      apt) pkgs="$apt_pkgs" ;;
      dnf) pkgs="$dnf_pkgs" ;;
      pacman) pkgs="$pacman_pkgs" ;;
    esac
    for pkg in $pkgs; do
      pkg_set["$pkg"]=1
    done
  done

  local -a install_packages=()
  local pkg
  for pkg in "${!pkg_set[@]}"; do
    install_packages+=("$pkg")
  done

  if ((${#install_packages[@]} == 0)); then
    warn "No package suggestions available for detected missing commands."
    return
  fi

  section "Installing missing packages"
  info "Package manager: $pkg_manager"
  info "Packages: ${install_packages[*]}"

  case "$pkg_manager" in
    apt)
      sudo apt-get update
      sudo apt-get install -y "${install_packages[@]}"
      ;;
    dnf)
      sudo dnf install -y "${install_packages[@]}"
      ;;
    pacman)
      sudo pacman -S --needed --noconfirm "${install_packages[@]}"
      ;;
  esac

  info "Dependency installation step completed."
}

# ---------------------------------------------------------------------------
# Collect configuration
# ---------------------------------------------------------------------------

section "Vela RemotePC Agent setup"
info "Installing to: $ROOT_DIR"
info "Existing $ENV_FILE will be overwritten."

# Load existing .env to pre-seed defaults BEFORE prompting
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE" || true
fi

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
prompt_required VPS_URL "Relay URL (domain or full URL)" ""
# Auto-prepend https:// if no scheme provided
if [[ "$VPS_URL" != http://* && "$VPS_URL" != https://* ]]; then
  VPS_URL="https://$VPS_URL"
  info "Using HTTPS: $VPS_URL"
fi

DEFAULT_AGENT_LABEL="${AGENT_NAME:-$(hostname | tr -cs 'A-Za-z0-9_.-' '-')}"
prompt_required AGENT_NAME "Agent label (shown in app)" "$DEFAULT_AGENT_LABEL"

# Keep only existing VPS-issued IDs for repair/reuse flows.
EXISTING_VPS_AGENT_ID="${AGENT_ID:-}"
if [[ ! "$EXISTING_VPS_AGENT_ID" =~ ^agt_ ]]; then
  EXISTING_VPS_AGENT_ID=""
fi

# AGENT_SECRET is issued by the relay on first registration; users don't set it.
EXISTING_AGENT_SECRET="${AGENT_SECRET:-${SECRET:-}}"
AGENT_SECRET=""
if [[ -n "$EXISTING_AGENT_SECRET" ]]; then
  read -rp "  Reuse existing agent credential from previous setup? [y/N]: " reuse_secret
  if [[ "${reuse_secret:-N}" =~ ^[Yy]([Ee][Ss])?$ ]]; then
    AGENT_SECRET="$EXISTING_AGENT_SECRET"
    info "Reusing existing agent credential."
  else
    info "A new pairing will be required after setup."
  fi
fi

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
  read -rp "  Allow access to the entire filesystem? Type 'I understand': " confirm_root
  [[ "$confirm_root" == "I understand" ]] || die "Setup cancelled. Choose narrower base directories."
fi

section "Spotify (optional)"

read -rp "  Do you want to configure Spotify? [y/N]: " answer
if [[ "${answer:-N}es" =~ ^[Yy][Ee][Ss]$ ]]; then
  prompt_required SPOTIFY_CLIENT_ID "Spotify Client ID"
  prompt_required SPOTIFY_CLIENT_SECRET "Spotify Client Secret"
  if [[ -z "${SPOTIFY_REDIRECT_URI:-}" ]]; then
    if [[ -n "$EXISTING_VPS_AGENT_ID" ]]; then
      SPOTIFY_REDIRECT_URI="${VPS_URL}/relay/${EXISTING_VPS_AGENT_ID}/callback"
    else
      SPOTIFY_REDIRECT_URI="${VPS_URL}/relay/your_agent_id_after_pairing/callback"
    fi
  fi
  info "Using Spotify redirect URI: $SPOTIFY_REDIRECT_URI"
else
  SPOTIFY_CLIENT_ID="${SPOTIFY_CLIENT_ID:-}"
  SPOTIFY_CLIENT_SECRET="${SPOTIFY_CLIENT_SECRET:-}"
  SPOTIFY_REDIRECT_URI="${SPOTIFY_REDIRECT_URI:-}"
fi

section "Security (optional)"

ASSISTANT_ACTION_PIN="${ASSISTANT_ACTION_PIN:-${VELA_ASSISTANT_ACTION_PIN:-}}"
if [[ -z "$ASSISTANT_ACTION_PIN" ]]; then
  read -rsp "  Assistant action PIN for high-risk operations (press Enter to skip): " answer; echo
  ASSISTANT_ACTION_PIN="${answer:-}"
fi

PKG_MANAGER="$(detect_pkg_manager)"
check_and_offer_system_dependencies "$PKG_MANAGER"

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

AGENT_ID="$EXISTING_VPS_AGENT_ID"
export USERNAME PASSWORD LOCAL_SERVICE_USERNAME LOCAL_SERVICE_PASSWORD
export VPS_URL AGENT_NAME AGENT_ID AGENT_SECRET PUBLIC_ADDRESS METADATA
export SERVER_HOST SERVER_PORT ALLOWED_BASE_DIRS ASSISTANT_ACTION_PIN
export CONFIG_FILE ENV_FILE
# Fireworks vars are optional; export whatever is already in the environment.
export FIREWORKS_API_KEY="${FIREWORKS_API_KEY:-}"
export VELA_FIREWORKS_API_URL="${VELA_FIREWORKS_API_URL:-}"
export VELA_FIREWORKS_MODEL="${VELA_FIREWORKS_MODEL:-}"

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

health_url = f"{vps_url.rstrip('/')}/health"
print(f"  Checking VPS at {health_url} …")
try:
    resp = requests.get(health_url, timeout=10)
except requests.exceptions.ConnectionError:
    sys.exit(f"Could not connect to {vps_url}. Ensure the VPS is running and reachable.")
except requests.exceptions.Timeout:
    sys.exit(f"Connection to {vps_url} timed out after 10 seconds.")
except requests.exceptions.RequestException as exc:
    sys.exit(f"Request failed: {exc}")

if resp.status_code == 200:
    data = resp.json()
    if data.get("status") != "ok":
        sys.exit(f"VPS health check failed: {data}")
    print("  VPS is reachable and healthy.")
elif resp.status_code == 404:
    sys.exit(f"VPS returned 404 Not Found at {health_url}. Check your relay URL.")
else:
    sys.exit(f"VPS returned {resp.status_code}: {resp.text}")
PY

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
            "accounts/fireworks/models/qwen3p7-plus")

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
    f"AGENT_NAME={os.environ.get('AGENT_NAME', '')}",
    f"AGENT_ID={os.environ['AGENT_ID']}",
    f"AGENT_SECRET={os.environ['AGENT_SECRET']}",
    f"ASSISTANT_ACTION_PIN={os.environ.get('ASSISTANT_ACTION_PIN', '')}",
    f"FIREWORKS_API_KEY='paste_your_key_here'",
    f"VELA_ASSISTANT_ENABLE_THINKING='false'",
    f"VELA_FIREWORKS_API_URL={fw_url}",
    f"VELA_FIREWORKS_MODEL={fw_model}",
    f"RECIPIENT_EMAIL='your_personal_email'",
    f"RESEND_API_KEY='your_resend_api_key'",
    f"RESEND_FROM_EMAIL='your_resend_email'",
]

if addr := os.environ.get("PUBLIC_ADDRESS", "").strip():
    lines.append(f"PUBLIC_ADDRESS={addr}")
if meta := os.environ.get("METADATA", "").strip():
    lines.append(f"METADATA={meta}")
if fw_key := os.environ.get("FIREWORKS_API_KEY", "").strip():
    lines.append(f"FIREWORKS_API_KEY={fw_key}")
lines.append(f"SPOTIFY_CLIENT_ID={os.environ.get('SPOTIFY_CLIENT_ID', '') or 'your_spotify_client_id_here'}")
lines.append(f"SPOTIFY_CLIENT_SECRET={os.environ.get('SPOTIFY_CLIENT_SECRET', '') or 'your_spotify_client_secret_here'}")
spotify_redirect = os.environ.get("SPOTIFY_REDIRECT_URI", "").strip()
if not spotify_redirect:
    agent_id = os.environ.get("AGENT_ID", "").strip()
    if agent_id:
        spotify_redirect = f"{os.environ['VPS_URL']}/relay/{agent_id}/callback"
    else:
        spotify_redirect = f"{os.environ['VPS_URL']}/relay/your_agent_id_after_pairing/callback"
lines.append(f"SPOTIFY_REDIRECT_URI={spotify_redirect}")

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
systemctl --user enable "$AGENT_SERVICE_NAME"
info "API service enabled and started."

restart_or_start_service() {
  local service="$1"
  if systemctl --user is-active --quiet "$service"; then
    systemctl --user restart "$service"
  else
    systemctl --user start "$service"
  fi
}

if [[ -n "$AGENT_SECRET" ]]; then
  restart_or_start_service "$AGENT_SERVICE_NAME"
  info "Agent service (re)started using existing credential."
else
  section "Agent pairing"
  info "Launching browser pairing flow now..."
  if "$VENV_DIR/bin/vela" --pair; then
    restart_or_start_service "$AGENT_SERVICE_NAME"
    info "Agent paired and service (re)started."
  else
    warn "Pairing did not complete. You can retry with: $VENV_DIR/bin/vela --pair"
    warn "Starting agent service anyway so it can retry in background."
    restart_or_start_service "$AGENT_SERVICE_NAME" || true
  fi
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

section "Setup complete"
info "Config:        $CONFIG_FILE"
info "Environment:   $ENV_FILE"
info "Service:       $SERVICE_PATH"
info "Agent service: $AGENT_SERVICE_PATH"
info "Local API:     http://127.0.0.1:$SERVER_PORT"

# ---------------------------------------------------------------------------
# Service status
# ---------------------------------------------------------------------------

section "Service status"

check_service() {
  local name="$1"
  if systemctl --user is-active --quiet "$name"; then
    echo "  ✓  $name   →  running"
  else
    echo "  ✗  $name   →  NOT running"
    warn "Start it with: systemctl --user start $name"
  fi
}

check_service "$SERVICE_NAME"
check_service "$AGENT_SERVICE_NAME"

# ---------------------------------------------------------------------------
# Service management help
# ---------------------------------------------------------------------------

section "Service management commands"
echo
info "  vela --start        — start both services"
info "  vela --stop         — stop both services"
info "  vela --enable       — enable+start both services"
info "  vela --status       — show service activity state"
info "  vela --logs         — tail vela + agent logs"
info "  vela --pair         — force browser pairing flow"
info "  vela --setup        — rerun interactive setup"
info "  vela-agent --start  — start agent service only"
info "  vela-agent --stop   — stop agent service only"
echo

# ---------------------------------------------------------------------------
# Next steps — what to use on your device
# ---------------------------------------------------------------------------

section "Connect from your Android device"
echo
echo "  │  VPS URL      :  $VPS_URL"
echo "  │  Agent label  :  $AGENT_NAME"
if [[ -n "$AGENT_ID" ]]; then
  echo "  │  Agent ID     :  $AGENT_ID"
fi
echo
if [[ -n "$AGENT_SECRET" ]]; then
  info "Existing credential was reused. No new pairing step is required."
else
  info "Pairing has been launched during setup. If needed, rerun it with: vela --pair"
  info "Watch logs with: journalctl --user -u vela-agent.service -f"
fi
