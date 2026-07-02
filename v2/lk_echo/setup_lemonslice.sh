#!/usr/bin/env bash
# Setup LemonSlice for Echo-Node.
# One-time setup: installs deps, creates FIFO, checks API keys.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/.venv"

echo ""
echo "╔════════════════════════════════════════════════════╗"
echo "║  Echo-Node × LemonSlice Setup                      ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""

# ── 1. Install Python deps ────────────────────────────────────────
echo "  [1/3] Installing Python dependencies..."
cd "$ROOT"
source "$VENV/bin/activate"
pip install -q "livekit-agents[lemonslice,openai,deepgram]" 2>&1 | tail -1
echo "        ✓ livekit-agents[lemonslice]"

# ── 2. Create FIFO ────────────────────────────────────────────────
echo "  [2/3] Creating IPC FIFO..."
FIFO="/tmp/echo-node-avatar.fifo"
if [ ! -p "$FIFO" ]; then
  mkfifo "$FIFO" 2>/dev/null || true
fi
if [ -p "$FIFO" ]; then
  echo "        ✓ $FIFO"
else
  echo "        ⚠ Could not create FIFO (may already be open)"
fi

# ── 3. Check API keys ─────────────────────────────────────────────
echo "  [3/3] Checking API keys..."
echo ""
echo "       ┌──────────────────────┬─────────────────────────┐"
echo "       │ Variable             │ Status                  │"
echo "       ├──────────────────────┼─────────────────────────┤"

check_key() {
  local var="$1" name="$2"
  if [ -n "${!var:-}" ]; then
    printf "       │ %-20s │ ✓ set                   │\n" "$name"
  else
    printf "       │ %-20s │ ✗ NOT SET               │\n" "$name"
  fi
}

check_key "LEMONSLICE_API_KEY" "LEMONSLICE_API_KEY"
check_key "OPENAI_API_KEY"    "OPENAI_API_KEY"
check_key "DEEPGRAM_API_KEY"  "DEEPGRAM_API_KEY"
check_key "ELEVEN_API_KEY"    "ELEVEN_API_KEY"

echo "       └──────────────────────┴─────────────────────────┘"
echo ""

# If .env doesn't exist, offer to create from template
ENV_FILE="$ROOT/lk_echo/.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "  Creating .env from template..."
  cp "$ROOT/lk_echo/.env.lemonslice" "$ENV_FILE"
  echo "        ✓ $ENV_FILE"
  echo "        ⚠ Edit it to add your API keys!"
  echo ""
fi

echo "  Setup complete! Run: ./lk_echo/run_lemonslice.sh"
echo ""
