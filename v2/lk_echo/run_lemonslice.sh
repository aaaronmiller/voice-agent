#!/usr/bin/env bash
# Echo-Node LemonSlice launcher.
#
# Starts: lk-server → agent (LemonSlice avatar) → client (desktop video viewer)
#
# Usage:
#   ./lk_echo/run_lemonslice.sh              # start everything
#   ./lk_echo/run_lemonslice.sh --attach     # start and attach tmux
#   ./lk_echo/run_lemonslice.sh --kill       # stop everything

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SESSION="echo-node-lemonslice"
LK_SERVER="$ROOT/vendor/lk-server"
LOG_DIR="$ROOT/logs"
VENV="$ROOT/.venv"
mkdir -p "$LOG_DIR"

# ── Load env ────────────────────────────────────────────────────────

# Load .env from the lk_echo/ directory (or fallback to repo root)
if [ -f "$ROOT/lk_echo/.env" ]; then
  set -a; source "$ROOT/lk_echo/.env"; set +a
elif [ -f "$ROOT/.env" ]; then
  set -a; source "$ROOT/.env"; set +a
fi

# ── Check requirements ─────────────────────────────────────────────

if [ ! -x "$LK_SERVER" ]; then
  echo "ERROR: lk-server not found at $LK_SERVER"
  echo "Run 'lk_echo/setup.sh' first to download it."
  exit 1
fi

if [ -z "${LEMONSLICE_API_KEY:-}" ]; then
  echo "ERROR: LEMONSLICE_API_KEY is not set"
  echo "Get one from https://lemonslice.com"
  exit 1
fi

if [ -z "${OPENAI_API_KEY:-}" ]; then
  echo "WARNING: OPENAI_API_KEY not set — LLM/TTS will fail"
fi

if [ -z "${DEEPGRAM_API_KEY:-}" ]; then
  echo "WARNING: DEEPGRAM_API_KEY not set — STT will fail"
fi

# ── Kill previous session ──────────────────────────────────────────

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Killing previous session..."
  tmux kill-session -t "$SESSION"
  sleep 1
fi
pkill -f "lk_echo/agent_lemonslice.py" 2>/dev/null || true
pkill -f "lk_echo/client_video.py" 2>/dev/null || true
pkill -f "lk-server" 2>/dev/null || true
sleep 1

# ── Start tmux session ─────────────────────────────────────────────

echo "Starting lk-server..."
tmux new-session -d -s "$SESSION" -n "lk-server" \
  "cd '$ROOT' && '$LK_SERVER' --dev --bind 127.0.0.1 --port 7880 2>&1 | tee '$LOG_DIR/lk-server.log'"

sleep 2

echo "Starting LemonSlice agent..."
tmux new-window -t "$SESSION" -n "agent" \
  "cd '$ROOT' && source env.sh 2>/dev/null; '$VENV/bin/python' -m lk_echo.agent_lemonslice dev 2>&1 | tee '$LOG_DIR/agent.log'"

sleep 3

echo "Starting video client..."
tmux new-window -t "$SESSION" -n "client" \
  "cd '$ROOT' && '$VENV/bin/python' -m lk_echo.client_video 2>&1 | tee '$LOG_DIR/client.log'"

echo ""
echo "╔════════════════════════════════════════════════════╗"
echo "║  Echo-Node + LemonSlice running!                   ║"
echo "║                                                    ║"
echo "║  tmux attach -t $SESSION      ║"
echo "║  logs: $LOG_DIR/                         ║"
echo "║                                                    ║"
echo "║  The avatar window should appear automatically.   ║"
echo "║  Speak to the mic — Jess will respond with        ║"
echo "║  realistic lip-synced video.                       ║"
echo "╚════════════════════════════════════════════════════╝"

if [[ "${1:-}" == "--attach" ]]; then
  tmux attach -t "$SESSION"
fi
