#!/usr/bin/env bash
# Echo-Node LemonSlice launcher.
#
# Two modes:
#
# MODE A: LiveKit Cloud (agent_lemonslice.py)
#   export LIVEKIT_URL=wss://your-project.livekit.cloud
#   export LIVEKIT_API_KEY=...
#   export LIVEKIT_API_SECRET=...
#   No local lk-server needed — LiveKit Cloud handles WebRTC + inference
#
# MODE B: Local lk-server (agent_lemonslice_local.py)
#   Uses lk-server --dev for WebRTC
#   Individual API keys for STT/LLM/TTS
#
# Usage:
#   ./lk_echo/run_lemonslice.sh              # auto-detect mode from env
#   ./lk_echo/run_lemonslice.sh --cloud      # force cloud mode
#   ./lk_echo/run_lemonslice.sh --local      # force local mode
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

if [ -f "$ROOT/lk_echo/.env" ]; then
  set -a; source "$ROOT/lk_echo/.env"; set +a
elif [ -f "$ROOT/.env" ]; then
  set -a; source "$ROOT/.env"; set +a
fi

# ── Detect mode ─────────────────────────────────────────────────────

MODE="auto"
if [[ "${1:-}" == "--cloud" ]]; then MODE="cloud"; shift; fi
if [[ "${1:-}" == "--local" ]]; then MODE="local"; shift; fi

# Auto-detect: if LIVEKIT_URL is ws:// or ws://localhost, use local mode
if [ "$MODE" = "auto" ]; then
  if echo "${LIVEKIT_URL:-}" | grep -qE '^ws://(127\.0\.0\.1|localhost)'; then
    MODE="local"
  elif [ -n "${LIVEKIT_URL:-}" ]; then
    MODE="cloud"
  else
    # Default to local
    MODE="local"
    LIVEKIT_URL=ws://127.0.0.1:7880
    LIVEKIT_API_KEY=devkey
    LIVEKIT_API_SECRET=secret
  fi
fi

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Echo-Node × LemonSlice  ($MODE mode)        ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── Check requirements ─────────────────────────────────────────────

if [ -z "${LEMONSLICE_API_KEY:-}" ]; then
  echo "ERROR: LEMONSLICE_API_KEY is not set"
  echo "Get one at https://lemonslice.com"
  echo "  or:  cp lk_echo/.env.lemonslice lk_echo/.env && \$EDITOR lk_echo/.env"
  exit 1
fi

if [ "$MODE" = "local" ]; then
  if [ ! -x "$LK_SERVER" ]; then
    echo "ERROR: lk-server not found at $LK_SERVER"
    echo "Run 'lk_echo/setup.sh' first to download it."
    exit 1
  fi
  AGENT_SCRIPT="lk_echo.agent_lemonslice_local"
  echo "  WebRTC: $LK_SERVER (local)"
  echo "  Agent:  $AGENT_SCRIPT (direct plugins)"
  echo ""

  if [ -z "${DEEPGRAM_API_KEY:-}" ]; then
    echo "WARNING: DEEPGRAM_API_KEY not set — STT will fail"
  fi
  if [ -z "${OPENAI_API_KEY:-}" ] || [ "${OPENAI_API_KEY:-}" = "dummy" ]; then
    echo "WARNING: OPENAI_API_KEY not valid — LLM/TTS will fail"
    echo "  Set OPENAI_API_KEY or LLM_API_KEY + TTS_API_KEY in .env"
  fi
else
  AGENT_SCRIPT="lk_echo.agent_lemonslice"
  echo "  WebRTC: $LIVEKIT_URL (LiveKit Cloud)"
  echo "  Agent:  $AGENT_SCRIPT (cloud inference)"
  echo ""

  if [ -z "${LIVEKIT_API_KEY:-}" ]; then
    echo "ERROR: LIVEKIT_API_KEY not set for cloud mode"
    exit 1
  fi
  if [ -z "${LIVEKIT_API_SECRET:-}" ]; then
    echo "ERROR: LIVEKIT_API_SECRET not set for cloud mode"
    exit 1
  fi
fi

# ── Kill previous session ──────────────────────────────────────────

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Killing previous session..."
  tmux kill-session -t "$SESSION"
  sleep 1
fi
pkill -f "lk_echo/agent_lemonslice" 2>/dev/null || true
pkill -f "lk_echo/client_video" 2>/dev/null || true
pkill -f "lk-server" 2>/dev/null || true
sleep 1

# ── Start processes ────────────────────────────────────────────────

if [ "$MODE" = "local" ]; then
  # ── Local mode: lk-server + agent + client ──
  echo "Starting lk-server (local WebRTC)..."
  tmux new-session -d -s "$SESSION" -n "lk-server" \
    "cd '$ROOT' && '$LK_SERVER' --dev --bind 127.0.0.1 --port 7880 2>&1 | tee '$LOG_DIR/lk-server.log'"
  sleep 2

  echo "Starting agent (direct plugins)..."
  tmux new-window -t "$SESSION" -n "agent" \
    "cd '$ROOT' && source env.sh 2>/dev/null; '$VENV/bin/python' -m $AGENT_SCRIPT dev 2>&1 | tee '$LOG_DIR/agent.log'"
  sleep 3
else
  # ── Cloud mode: agent only (lk-server not needed) ──
  echo "Starting agent (LiveKit Cloud inference)..."
  tmux new-session -d -s "$SESSION" -n "agent" \
    "cd '$ROOT' && source env.sh 2>/dev/null; '$VENV/bin/python' -m $AGENT_SCRIPT dev 2>&1 | tee '$LOG_DIR/agent.log'"
  sleep 3
fi

echo "Starting video client..."
tmux new-window -t "$SESSION" -n "client" \
  "cd '$ROOT' && '$VENV/bin/python' -m lk_echo.client_video 2>&1 | tee '$LOG_DIR/client.log'"

echo ""
echo "  tmux:  tmux attach -t $SESSION"
echo "  logs:  $LOG_DIR/"
echo ""

if [[ "${1:-}" == "--attach" ]]; then
  tmux attach -t "$SESSION"
fi
