#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Vela RemotePC Agent — bootstrap into a venv, then run fresh-start setup
# ---------------------------------------------------------------------------

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"

section() { echo; echo "── $* ──"; }
info()    { echo "  $*"; }
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

section "Fresh setup"
exec "$VENV_DIR/bin/vela" --setup
