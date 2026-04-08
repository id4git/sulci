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

# ── langchain integration (optional — installs langchain-core only) ───────────
echo "→ Installing LangChain integration"
pip install --quiet -e ".[langchain]"

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

# ── verify imports ────────────────────────────────────────────────────────────
echo "\n→ Verifying install"
python3 -c "
from sulci import Cache, connect
import sulci
print(f'  version            = {sulci._SDK_VERSION}')
print(f'  Cache              = ok')
print(f'  connect            = ok')
print(f'  _telemetry_enabled = {sulci._telemetry_enabled}')
"

# ── smoke tests ───────────────────────────────────────────────────────────────
echo "\n→ Running smoke tests"

echo ""
echo "── Core ────────────────────────────────────────────────────────────────"
python3 smoke_test.py

echo ""
echo "── LangChain integration ───────────────────────────────────────────────"
python3 smoke_test_langchain.py

echo "✅ sulci-oss setup complete"
echo ""
echo "Next steps:"
echo "  python -m pytest tests/ -v          # run full test suite"
echo "  make smoke                          # re-run all smoke tests"
echo "  make test                           # run core tests only"
echo "  make test-integrations              # run integration tests"
