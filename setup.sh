#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Vela RemotePC Agent — bootstrap into a venv, then run fresh-start setup
# ---------------------------------------------------------------------------

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"

section() { echo; echo "── $* ──"; }
info()    { echo "  $*"; }
warn()    { echo "  WARNING: $*" >&2; }
die()     { echo "  ERROR: $*" >&2; exit 1; }

section "Vela bootstrap"
info "Installing to: $ROOT_DIR"
info "Setup always starts fresh: wipes relay + local auth caches, pairs, then restarts services."

cd "$ROOT_DIR"

if [[ ! -d "$VENV_DIR" ]]; then
  section "Creating virtualenv"
  python3 -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

section "Installing package"
pip install --upgrade pip
pip install -e .

section "User CLI links"
# Make `vela` / `vela-agent` available outside the venv via ~/.local/bin
LOCAL_BIN="$HOME/.local/bin"
mkdir -p "$LOCAL_BIN"
for cmd in vela vela-agent; do
  src="$VENV_DIR/bin/$cmd"
  dest="$LOCAL_BIN/$cmd"
  if [[ -x "$src" ]]; then
    ln -sfn "$src" "$dest"
    info "Linked $dest -> $src"
  else
    warn "Missing $src; skip CLI link for $cmd"
  fi
done
case ":$PATH:" in
  *":$LOCAL_BIN:"*) ;;
  *)
    warn "$LOCAL_BIN is not on PATH. Add this to your shell profile:"
    info "export PATH=\"\$HOME/.local/bin:\$PATH\""
    ;;
esac

section "Fresh setup"
exec "$VENV_DIR/bin/vela" --setup
