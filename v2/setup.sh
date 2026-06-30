#!/usr/bin/env bash
# Echo-Node v2 — Cross-platform setup (Linux, macOS, WSL2)
#
# Usage:
#   chmod +x setup.sh && ./setup.sh
#
# What it does:
#   1. Detects platform (linux / darwin / wsl2)
#   2. Installs system dependencies (apt/brew)
#   3. Creates Python venv + installs packages
#   4. Downloads Kokoro TTS models
#   5. Downloads Rhubarb lip-sync binary (platform-specific)
#   6. Downloads OpenWakeWord wake word models
#   7. Creates default config.yaml (platform-appropriate)
#
# Re-run safely — downloads are skipped if files exist.

set -euo pipefail
shopt -s nullglob

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# ── Detect platform ─────────────────────────────────────────────────

PLATFORM="linux"
IS_WSL=false
IS_MAC=false

case "$(uname -s)" in
  Darwin)
    PLATFORM="darwin"
    IS_MAC=true
    ;;
  Linux)
    if grep -qi microsoft /proc/version 2>/dev/null; then
      PLATFORM="wsl2"
      IS_WSL=true
    fi
    ;;
  *)
    echo "Unsupported platform: $(uname -s)" >&2
    exit 1
    ;;
esac

echo "┌─────────────────────────────────────┐"
echo "│  Echo-Node v2  —  Platform: $PLATFORM │"
echo "└─────────────────────────────────────┘"
echo

# ── System dependencies ─────────────────────────────────────────────

install_system_deps() {
  local missing=()

  if $IS_MAC; then
    # macOS — use Homebrew
    if ! command -v brew &>/dev/null; then
      echo "Homebrew is required. Install from https://brew.sh" >&2
      exit 1
    fi
    for pkg in espeak-ng portaudio; do
      if ! brew list "$pkg" &>/dev/null; then
        echo "  Installing $pkg..."
        brew install "$pkg"
      else
        echo "  ✓ $pkg"
      fi
    done
    # On macOS, audio uses CoreAudio via sounddevice (no ALSA needed)
    return
  fi

  # Linux / WSL2
  for cmd in arecord aplay; do
    if ! command -v "$cmd" &>/dev/null; then
      missing+=("$cmd")
    fi
  done
  if ! command -v espeak-ng &>/dev/null; then
    missing+=("espeak-ng")
  fi

  if [[ ${#missing[@]} -gt 0 ]]; then
    echo "  Installing system packages: ${missing[*]}"
    if command -v apt &>/dev/null; then
      sudo apt update -qq
      for pkg in "${missing[@]}"; do
        case "$pkg" in
          arecord|aplay) sudo apt install -y -qq alsa-utils ;;
          espeak-ng)     sudo apt install -y -qq espeak-ng ;;
        esac
      done
    elif command -v pacman &>/dev/null; then
      for pkg in "${missing[@]}"; do
        case "$pkg" in
          arecord|aplay) sudo pacman -S --noconfirm alsa-utils ;;
          espeak-ng)     sudo pacman -S --noconfirm espeak-ng ;;
        esac
      done
    else
      echo "  WARNING: No apt/pacman found. Install manually: ${missing[*]}" >&2
    fi
  else
    echo "  ✓ All system packages present"
  fi
}

echo "── System dependencies ──"
install_system_deps
echo

# ── Python version check ───────────────────────────────────────────

PYTHON_BIN=""
for candidate in python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; exit(0 if sys.version_info >= (3,11) else 1)' &>/dev/null; then
      PYTHON_BIN="$candidate"
      break
    fi
  fi
done

if [[ -z "$PYTHON_BIN" ]]; then
  echo "ERROR: Python 3.11+ required. Install via brew (macOS) or apt (Linux)." >&2
  exit 1
fi
echo "── Python $($PYTHON_BIN --version) ──"
echo

# ── Python virtual environment ──────────────────────────────────────

echo "── Virtual environment ──"
if [[ -d .venv ]]; then
  echo "  ✓ .venv exists (reusing)"
else
  "$PYTHON_BIN" -m venv .venv
  echo "  Created .venv"
fi

# Fix pip path (macOS has different venv structure sometimes)
VENV_PYTHON=".venv/bin/python"
if $IS_MAC && [[ ! -x "$VENV_PYTHON" ]]; then
  # macOS venv might use python3 in a different location
  VENV_PYTHON=".venv/bin/python3"
fi
echo

# ── Install Python packages ─────────────────────────────────────────

echo "── Python packages ──"
$VENV_PYTHON -m pip install --upgrade pip -q

# Install core dependencies
$VENV_PYTHON -m pip install \
  numpy>=1.26 \
  huggingface_hub>=0.23 \
  kokoro-onnx>=0.5.0 \
  onnx-asr>=0.11.0 \
  onnxruntime>=1.18 \
  openwakeword>=0.6.0 \
  pyyaml>=6.0 \
  requests>=2.31 \
  soundfile>=0.12 \
  sounddevice>=0.5 \
  pynput>=1.7 \
  pyyaml>=6.0 \
  -q

# faster-whisper (CT-Translate, may need extra deps on macOS)
$VENV_PYTHON -m pip install faster-whisper -q 2>/dev/null || {
  echo "  WARNING: faster-whisper install failed (common on Apple Silicon)."
  echo "  Falling back to onnx-asr STT (already installed)."
  echo "  The assistant will use the 'parakeet' STT provider instead."
}

# Avatar (PyQt6 — optional, skips if fails)
$VENV_PYTHON -m pip install PyQt6 Pillow -q 2>/dev/null || {
  echo "  WARNING: PyQt6 install failed (avatar disabled)."
  echo "  Install manually: brew install pyqt (macOS) or pip install PyQt6"
}

echo "  ✓ Python packages installed"
echo

# ── Download Kokoro TTS models ──────────────────────────────────────

echo "── Kokoro TTS models ──"
mkdir -p models/kokoro

download() {
  local url="$1" out="$2"
  if [[ -f "$out" ]]; then
    echo "  ✓ $out"
    return
  fi
  echo "  Downloading $(basename "$out")..."
  curl -sL "$url" -o "$out"
}

download \
  "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx" \
  "models/kokoro/kokoro-v1.0.onnx"

download \
  "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin" \
  "models/kokoro/voices-v1.0.bin"
echo

# ── Download Rhubarb lip-sync binary ────────────────────────────────

echo "── Rhubarb lip-sync ──"
mkdir -p vendor/rhubarb

detect_arch() {
  local arch
  arch="$(uname -m)"
  case "$arch" in
    x86_64|amd64)  echo "x86_64" ;;
    aarch64|arm64) echo "arm64"  ;;
    armv7l)        echo "armv7l" ;;
    *)             echo "$arch"  ;;
  esac
}

RHUBARB_VERSION="1.14.0"
RHUBARB_DIR="vendor/rhubarb"
RHUBARB_BIN="rhubarb"
RHUBARB_URL=""

case "$PLATFORM" in
  linux|wsl2)
    RHUBARB_URL="https://github.com/DanielSWolf/rhubarb-lip-sync/releases/download/v${RHUBARB_VERSION}/Rhubarb-Lip-Sync-${RHUBARB_VERSION}-Linux.zip"
    RHUBARB_EXTRACTED="Rhubard-Lip-Sync-${RHUBARB_VERSION}-Linux"
    ;;
  darwin)
    RHUBARB_URL="https://github.com/DanielSWolf/rhubarb-lip-sync/releases/download/v${RHUBARB_VERSION}/Rhubarb-Lip-Sync-${RHUBARB_VERSION}-macOS.zip"
    RHUBARB_EXTRACTED="Rhubarb-Lip-Sync-${RHUBARB_VERSION}-macOS"
    ;;
esac

if [[ -f "$RHUBARB_DIR/$RHUBARB_BIN" ]] || [[ -f "$RHUBARB_DIR/${RHUBARB_BIN}.exe" ]]; then
  echo "  ✓ Rhubarb binary present"
else
  if [[ -n "$RHUBARB_URL" ]]; then
    echo "  Downloading Rhubarb v${RHUBARB_VERSION}..."
    local_zip="/tmp/rhubarb-${RHUBARB_VERSION}.zip"
    curl -sL "$RHUBARB_URL" -o "$local_zip"
    unzip -q -o "$local_zip" -d /tmp/
    # Find and move the binary
    found_bin=$(find /tmp -name "rhubarb" -o -name "rhubarb.exe" 2>/dev/null | head -1)
    if [[ -n "$found_bin" ]]; then
      cp "$found_bin" "$RHUBARB_DIR/$RHUBARB_BIN"
      chmod +x "$RHUBARB_DIR/$RHUBARB_BIN"
      echo "  ✓ Rhubarb installed"
    else
      echo "  WARNING: Could not find Rhubarb binary in extracted files"
    fi
    rm -f "$local_zip"
    rm -rf "/tmp/${RHUBARB_EXTRACTED}" 2>/dev/null || true
  else
    echo "  Skipping Rhubarb (no release for $(uname -s))"
  fi
fi
echo

# ── Download OpenWakeWord models ─────────────────────────────────────

echo "── OpenWakeWord models ──"
$VENV_PYTHON -c "
from openwakeword.utils import download_models
download_models(model_names=['hey_rhasspy'])
print('  ✓ hey_rhasspy model')
" 2>&1 || echo "  WARNING: wake word download failed (can skip, models auto-download on first run)"
echo

# ── Create default config ───────────────────────────────────────────

echo "── Configuration ──"
if [[ -f config.yaml ]]; then
  echo "  ✓ config.yaml exists (keeping)"
else
  if [[ -f config.example.yaml ]]; then
    cp config.example.yaml config.yaml
    echo "  Created config.yaml from config.example.yaml"
  else
    echo "  Creating default config.yaml for $PLATFORM..."
    if [[ -f config.wsl.yaml ]]; then
      if $IS_MAC; then
        # macOS config — use sounddevice backend, no arecord
        sed 's/backend: alsa/backend: sounddevice/' config.wsl.yaml > config.yaml
      else
        cp config.wsl.yaml config.yaml
      fi
    else
      echo "  WARNING: no template config found. Copy config from another system."
    fi
  fi
fi
echo

# ── Create .env if missing ──────────────────────────────────────────

if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
    echo "── .env ──"
    echo "  Created .env from .env.example"
    echo "  ➜  Edit .env to add your API keys"
    echo
  fi
fi

# ── Create logs directory ───────────────────────────────────────────

mkdir -p logs

# ── Done ────────────────────────────────────────────────────────────

echo "┌─────────────────────────────────────────────────────┐"
echo "│  Echo-Node v2 setup complete                        │"
echo "├─────────────────────────────────────────────────────┤"
if $IS_MAC; then
  echo "│  Start with:  source env.sh && ./run.sh            │"
  echo "│  Or:          ./run.sh --config config.yaml        │"
else
  echo "│  Start with:  ./run.sh                             │"
fi
echo "│                                                     │"
echo "│  tmux:        echo-node  (start + attach)           │"
echo "│  Attach:      echo-node-attach                      │"
echo "│  Hotkey:      Ctrl+Shift+Q  (GNOME)                 │"
echo "├─────────────────────────────────────────────────────┤"
echo "│  Config:      config.yaml                           │"
echo "│  Logs:        logs/                                 │"
echo "│  Models:      models/kokoro/                        │"
echo "│  Rhubarb:     vendor/rhubarb/                       │"
echo "└─────────────────────────────────────────────────────┘"
