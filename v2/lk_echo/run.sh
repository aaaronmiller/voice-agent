#!/usr/bin/env bash
# Echo-Node LiveKit launcher.
#
# Starts the local LiveKit server, the agent (voice pipeline), and the
# client (local audio bridge) in separate tmux panes or background processes.
#
# Usage:
#   ./livekit/run.sh              # start everything
#   ./livekit/run.sh --attach     # start and attach tmux
#   ./livekit/run.sh --kill       # stop everything

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SESSION="echo-node-livekit"
LK_SERVER="$ROOT/vendor/lk-server"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"

# ── Check requirements ─────────────────────────────────────────────

if [ ! -x "$LK_SERVER" ]; then
  echo "ERROR: lk-server not found at $LK_SERVER"
  echo "Run 'setup_livekit.sh' first to download it."
  exit 1
fi

# Check API keys
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
pkill -f "lk_echo/agent.py" 2>/dev/null || true
pkill -f "lk_echo/client.py" 2>/dev/null || true
pkill -f "lk-server" 2>/dev/null || true
sleep 1

# ── Generate LiveKit dev config ────────────────────────────────────

# lk-server --dev works without a config file when using dev keys
# devkey/secret are the defaults

# ── Start tmux session ─────────────────────────────────────────────

tmux new-session -d -s "$SESSION" -n "lk-server" \
  "cd '$ROOT' && '$LK_SERVER' --dev --bind 127.0.0.1 --port 7880 2>&1 | tee '$LOG_DIR/lk-server.log'"

sleep 2

tmux new-window -t "$SESSION" -n "agent" \
  "cd '$ROOT' && source env.sh 2>/dev/null; .venv/bin/python -m lk_echo.agent 2>&1 | tee '$LOG_DIR/agent.log'"

sleep 3

tmux new-window -t "$SESSION" -n "client" \
  "cd '$ROOT' && source env.sh 2>/dev/null; .venv/bin/python -m lk_echo.client 2>&1 | tee '$LOG_DIR/client.log'"

echo "Echo-Node LiveKit started"
echo "  tmux attach -t $SESSION"
echo "  logs: $LOG_DIR/{lk-server,agent,client}.log"

if [[ "${1:-}" == "--attach" ]]; then
  tmux attach -t "$SESSION"
fi
