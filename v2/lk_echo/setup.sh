#!/usr/bin/env bash
# Setup LiveKit server for Echo-Node.
# Downloads lk-server binary and verifies Python dependencies.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$ROOT/vendor"
mkdir -p "$VENDOR"

echo "=== Echo-Node LiveKit Setup ==="

# ── 1. Download lk-server ──────────────────────────────────────────
LK_BIN="$VENDOR/lk-server"
if [ ! -x "$LK_BIN" ]; then
  echo "Downloading lk-server..."
  
  # Detect platform
  OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
  ARCH="$(uname -m)"
  case "$ARCH" in
    x86_64|amd64) ARCH="amd64" ;;
    aarch64|arm64) ARCH="arm64" ;;
  esac
  
  # Get latest version
  LK_VERSION=$(curl -sL "https://api.github.com/repos/livekit/livekit/releases/latest" 2>/dev/null \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['tag_name'])" 2>/dev/null || echo "v1.13.2")
  LK_VER="${LK_VERSION#v}"
  
  URL="https://github.com/livekit/livekit/releases/download/${LK_VERSION}/livekit_${LK_VER}_${OS}_${ARCH}.tar.gz"
  echo "  Downloading: $URL"
  
  curl -sL "$URL" -o /tmp/lk-server.tar.gz
  tar xzf /tmp/lk-server.tar.gz -C /tmp
  mv /tmp/livekit-server "$LK_BIN"
  chmod +x "$LK_BIN"
  rm -f /tmp/lk-server.tar.gz
  echo "  Installed lk-server v${LK_VER} ($(ls -lh "$LK_BIN" | awk '{print $5}'))"
else
  echo "  lk-server already installed"
fi

# ── 2. Install Python deps ─────────────────────────────────────────
echo "Installing Python dependencies..."
cd "$ROOT"
source .venv/bin/activate
pip install -q "livekit-agents[openai,deepgram]" 2>&1 | tail -1
echo "  Done"

# ── 3. Check API keys ──────────────────────────────────────────────
echo ""
echo "=== Environment Check ==="
echo "  LIVEKIT_URL=ws://127.0.0.1:7880"
echo "  LIVEKIT_API_KEY=devkey"
echo "  LIVEKIT_API_SECRET=secret"
echo ""
if [ -n "${OPENAI_API_KEY:-}" ]; then
  echo "  ✓ OPENAI_API_KEY is set"
else
  echo "  ✗ OPENAI_API_KEY is NOT set — LLM/TTS will fail"
fi
if [ -n "${DEEPGRAM_API_KEY:-}" ]; then
  echo "  ✓ DEEPGRAM_API_KEY is set"
else
  echo "  ✗ DEEPGRAM_API_KEY is NOT set — STT will fail"
fi

echo ""
echo "Setup complete! Run: ./livekit/run.sh"
