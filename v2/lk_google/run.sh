#!/usr/bin/env bash
# Echo-Node Google Voice Agent launcher.
#
# Uses Gemini Multimodal Live API for voice-in → voice-out.
# No separate STT/LLM/TTS needed — Gemini handles everything.
# Self-hosted lk-server for WebRTC.
#
# You already have GOOGLE_API_KEY set. That's all you need!
#
# Usage:
#   ./lk_google/run.sh                  # start everything
#   ./lk_google/run.sh --attach         # start and attach tmux
#   ./lk_google/run.sh --kill           # stop everything
#   ./lk_google/run.sh --no-avatar      # audio only (no LemonSlice)
#   ./lk_google/run.sh --no-video       # audio only (no client window)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SESSION="echo-node-google"
LK_SERVER="$ROOT/vendor/lk-server"
LOG_DIR="$ROOT/logs"
VENV="$ROOT/.venv"
mkdir -p "$LOG_DIR"

# ── Load env ────────────────────────────────────────────────────────

if [ -f "$ROOT/lk_google/.env" ]; then
  set -a; source "$ROOT/lk_google/.env"; set +a
fi

# ── Flags ───────────────────────────────────────────────────────────

NO_AVATAR=false
NO_VIDEO=false
ATTACH=""
for arg in "$@"; do
  case "$arg" in
    --attach) ATTACH="--attach" ;;
    --kill) 
      tmux kill-session -t "$SESSION" 2>/dev/null || true
      pkill -f "lk_google" 2>/dev/null || true
      pkill -f "lk-server" 2>/dev/null || true
      echo "Killed."
      exit 0
      ;;
    --no-avatar) NO_AVATAR=true ;;
    --no-video) NO_VIDEO=true ;;
  esac
done

# ── Check requirements ─────────────────────────────────────────────

if [ ! -x "$LK_SERVER" ]; then
  echo "ERROR: lk-server not found at $LK_SERVER"
  echo "Run 'lk_echo/setup.sh' first to download it."
  exit 1
fi

if [ -z "${GOOGLE_API_KEY:-}" ]; then
  echo "ERROR: GOOGLE_API_KEY is not set"
  echo "You can find it in your environment:"
  echo "  echo \$GOOGLE_API_KEY"
  exit 1
fi

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  Echo-Node × Google Gemini                           ║"
echo "║  Voice-in → Voice-out via Multimodal Live API        ║"
echo "║  No STT/LLM/TTS pipeline needed — Gemini does it all ║"
echo "║                                                      ║"
echo "║  GOOGLE_API_KEY: ✓ set                               ║"
if $NO_AVATAR || [ -z "${LEMONSLICE_API_KEY:-}" ]; then
  echo "║  Avatar: audio-only (no video)                       ║"
else
  echo "║  Avatar: LemonSlice ✓                                ║"
fi
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Kill previous session ──────────────────────────────────────────

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Killing previous session..."
  tmux kill-session -t "$SESSION"
  sleep 1
fi
pkill -f "lk_google" 2>/dev/null || true
pkill -f "lk-server" 2>/dev/null || true
sleep 1

# ── Start lk-server ───────────────────────────────────────────────

echo "Starting lk-server (local WebRTC)..."
tmux new-session -d -s "$SESSION" -n "lk-server" \
  "cd '$ROOT' && '$LK_SERVER' --dev --bind 127.0.0.1 --port 7880 2>&1 | tee '$LOG_DIR/lk-server.log'"
sleep 2

# ── Start agent ───────────────────────────────────────────────────

AGENT_ENV=""
if $NO_AVATAR || [ -z "${LEMONSLICE_API_KEY:-}" ]; then
  AGENT_ENV="LEMONSLICE_API_KEY="
fi

echo "Starting Gemini agent..."
tmux new-window -t "$SESSION" -n "agent" \
  "cd '$ROOT' && source env.sh 2>/dev/null; $AGENT_ENV '$VENV/bin/python' -m lk_google.agent dev 2>&1 | tee '$LOG_DIR/agent.log'"
sleep 3

# ── Start video client (optional) ─────────────────────────────────

if ! $NO_VIDEO; then
  if $NO_AVATAR || [ -z "${LEMONSLICE_API_KEY:-}" ]; then
    echo "Starting audio-only client..."
    echo "  (no avatar video — just voice through speakers)"
  else
    echo "Starting video client..."
  fi
  tmux new-window -t "$SESSION" -n "client" \
    "cd '$ROOT' && '$VENV/bin/python' -m lk_google.client_video 2>&1 | tee '$LOG_DIR/client.log'"
fi

echo ""
echo "  tmux attach -t $SESSION"
echo "  logs: $LOG_DIR/"
echo ""

if [ "$ATTACH" = "--attach" ]; then
  tmux attach -t "$SESSION"
fi
