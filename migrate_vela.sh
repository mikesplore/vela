#!/usr/bin/env bash
# migrate_vela.sh — Reorganises the Vela flat layout into a FastAPI app-package structure.
# Run from the project root:  bash migrate_vela.sh
# A full backup is created at ../vela_backup_<timestamp> before anything is touched.

set -euo pipefail

PROJECT_ROOT="$(pwd)"
BACKUP_DIR="../vela_backup_$(date +%Y%m%d_%H%M%S)"

# ── 0. Sanity check ────────────────────────────────────────────────────────────
if [[ ! -f "$PROJECT_ROOT/main.py" ]]; then
  echo "ERROR: Run this script from the vela project root (where main.py lives)."
  exit 1
fi

# ── 1. Backup ──────────────────────────────────────────────────────────────────
echo "→ Backing up to $BACKUP_DIR …"
cp -r "$PROJECT_ROOT" "$BACKUP_DIR"
echo "  Backup done."

# ── 2. Create new directory skeleton ──────────────────────────────────────────
echo "→ Creating app/ package …"
mkdir -p "$PROJECT_ROOT/app/routers"

# ── 3. Move core modules into app/ ────────────────────────────────────────────
CORE_MODULES=(
  agent.py
  auth.py
  config.py
  dependencies.py
  errors.py
  middleware.py
  prompts.py
  rate_limiter.py
  main.py
)

for f in "${CORE_MODULES[@]}"; do
  if [[ -f "$PROJECT_ROOT/$f" ]]; then
    echo "  mv $f → app/$f"
    mv "$PROJECT_ROOT/$f" "$PROJECT_ROOT/app/$f"
  else
    echo "  SKIP (not found): $f"
  fi
done

# ── 4. Move routers ────────────────────────────────────────────────────────────
echo "→ Moving routers/ contents into app/routers/ …"
if [[ -d "$PROJECT_ROOT/routers" ]]; then
  for f in "$PROJECT_ROOT/routers/"*.py; do
    fname="$(basename "$f")"
    echo "  mv routers/$fname → app/routers/$fname"
    mv "$f" "$PROJECT_ROOT/app/routers/$fname"
  done
  rmdir "$PROJECT_ROOT/routers" 2>/dev/null || true
fi

# ── 5. Create app/__init__.py ─────────────────────────────────────────────────
echo "→ Writing app/__init__.py …"
cat > "$PROJECT_ROOT/app/__init__.py" << 'PYEOF'
"""Vela — PC remote-control agent."""
PYEOF

# ── 6. Rewrite imports in every Python file under app/ ────────────────────────
echo "→ Rewriting imports …"

# Mapping: bare module name → new fully-qualified path
# Format: "old_bare_import|new_import"
REWRITES=(
  "from config import|from app.config import"
  "import config|import app.config as config"
  "from prompts import|from app.prompts import"
  "import prompts|import app.prompts as prompts"
  "from errors import|from app.errors import"
  "import errors|import app.errors as errors"
  "from auth import|from app.auth import"
  "import auth|import app.auth as auth"
  "from agent import|from app.agent import"
  "import agent|import app.agent as agent"
  "from dependencies import|from app.dependencies import"
  "import dependencies|import app.dependencies as dependencies"
  "from middleware import|from app.middleware import"
  "import middleware|import app.middleware as middleware"
  "from rate_limiter import|from app.rate_limiter import"
  "import rate_limiter|import app.rate_limiter as rate_limiter"
  "from routers import|from app.routers import"
  "import routers|import app.routers as routers"
  # routers' own relative imports — e.g. from auth import verify_token
  # are now intra-package, handled by the prefix rules above; relative
  # imports inside routers/ stay as-is (they already use bare names which
  # the above rules cover).
)

rewrite_file() {
  local file="$1"
  for rule in "${REWRITES[@]}"; do
    local old="${rule%%|*}"
    local new="${rule##*|}"
    # Use a temp file to avoid sed -i portability issues (macOS vs Linux)
    sed "s|${old}|${new}|g" "$file" > "$file.tmp" && mv "$file.tmp" "$file"
  done
}

while IFS= read -r -d '' pyfile; do
  rewrite_file "$pyfile"
done < <(find "$PROJECT_ROOT/app" -name "*.py" -print0)

# ── 7. Fix uvicorn target in app/main.py ──────────────────────────────────────
echo "→ Patching uvicorn app string in app/main.py …"
sed -i 's|"main:app"|"app.main:app"|g' "$PROJECT_ROOT/app/main.py"

# ── 8. Create root run.py entrypoint ──────────────────────────────────────────
echo "→ Writing run.py …"
cat > "$PROJECT_ROOT/run.py" << 'PYEOF'
"""Project entrypoint — keeps the root clean."""
from app.main import main

if __name__ == "__main__":
    main()
PYEOF

# ── 9. Move tests (no import rewriting needed — conftest handles paths) ────────
# Tests stay at project root; add app/ to sys.path via conftest if needed.
echo "→ Tests remain in tests/ (no move required)."

# ── 10. Patch conftest.py to ensure app/ is importable ────────────────────────
CONFTEST="$PROJECT_ROOT/tests/conftest.py"
if [[ -f "$CONFTEST" ]]; then
  # Prepend sys.path insert only if not already present
  if ! grep -q "sys.path.insert" "$CONFTEST"; then
    echo "→ Patching tests/conftest.py with sys.path …"
    TMP=$(mktemp)
    cat > "$TMP" << 'PYEOF'
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PYEOF
    cat "$CONFTEST" >> "$TMP"
    mv "$TMP" "$CONFTEST"
  fi
fi

# ── 11. Summary ───────────────────────────────────────────────────────────────
echo ""
echo "✓ Migration complete. New layout:"
echo ""
echo "  vela/"
echo "  ├── app/"
echo "  │   ├── __init__.py"
echo "  │   ├── main.py"
echo "  │   ├── config.py"
echo "  │   ├── auth.py"
echo "  │   ├── agent.py"
echo "  │   ├── dependencies.py"
echo "  │   ├── errors.py"
echo "  │   ├── middleware.py"
echo "  │   ├── prompts.py"
echo "  │   ├── rate_limiter.py"
echo "  │   └── routers/"
echo "  │       └── *.py"
echo "  ├── tests/"
echo "  ├── run.py             ← new entrypoint"
echo "  ├── config.yaml"
echo "  ├── pyproject.toml"
echo "  └── requirements.txt"
echo ""
echo "  Start with:  python run.py"
echo "  Or:          uvicorn app.main:app --reload"
echo ""
echo "  Backup at:   $BACKUP_DIR"
