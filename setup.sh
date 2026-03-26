#!/usr/bin/env zsh
# sulci-oss — local dev setup
# Run once after cloning: ./setup.sh

set -e
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
echo "Setting up sulci-oss at: $SCRIPT_DIR"

# ── venv ──────────────────────────────────────────────────────────────────────
echo "\n→ Creating venv at .venv"
cd "$SCRIPT_DIR"
python3 -m venv .venv
source .venv/bin/activate
pip install --quiet --upgrade pip

# ── dependencies ──────────────────────────────────────────────────────────────
echo "→ Installing dependencies"
pip install --quiet -e ".[sqlite,cloud]"
pip install --quiet pytest pytest-cov httpx

# ── .envrc ────────────────────────────────────────────────────────────────────
if command -v direnv &> /dev/null; then
  cat > .envrc << 'ENVRC'
source .venv/bin/activate
if [ -f .env ]; then
  dotenv .env
fi
ENVRC
  direnv allow .
  echo "→ direnv configured"
fi

# ── verify ────────────────────────────────────────────────────────────────────
echo "\n→ Verifying install"
python3 -c "
from sulci import Cache, connect
import sulci
print(f'  version            = {sulci._SDK_VERSION}')
print(f'  Cache              = ok')
print(f'  connect            = ok')
print(f'  _telemetry_enabled = {sulci._telemetry_enabled}')
"

echo "\n✅ sulci-oss setup complete"
echo ""
echo "Next steps:"
echo "  python -m pytest tests/ -v"
