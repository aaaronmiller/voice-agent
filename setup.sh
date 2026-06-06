#!/usr/bin/env bash
set -euo pipefail

echo "Echo-Node Local Voice MVP setup"
echo "==============================="

if ! command -v python3.11 >/dev/null 2>&1; then
  echo "ERROR: python3.11 is required for the local audio/ML environment." >&2
  exit 1
fi

if ! command -v espeak-ng >/dev/null 2>&1; then
  echo "ERROR: espeak-ng is required for local TTS." >&2
  exit 1
fi

if ! command -v aplay >/dev/null 2>&1; then
  echo "ERROR: aplay is required for local TTS playback." >&2
  exit 1
fi

if ! command -v ollama >/dev/null 2>&1; then
  echo "WARNING: ollama was not found; command/time/repeat responses will still work."
fi

echo
echo "Creating Python 3.11 virtual environment..."
python3.11 -m venv .venv
source .venv/bin/activate

echo
echo "Installing Python dependencies..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo
echo "Installing OpenWakeWord shared resources..."
python - <<'PY'
from openwakeword.utils import download_models

download_models(model_names=["__custom_only__"])
PY

echo
echo "Creating config.yaml..."
if [[ ! -f config.yaml ]]; then
  cp config.example.yaml config.yaml
  echo "Created config.yaml"
else
  echo "config.yaml already exists"
fi

echo
echo "Checking local wake-word models..."
python - <<'PY'
from pathlib import Path
import yaml

config = yaml.safe_load(Path("config.yaml").read_text()) or {}
missing = [
    path for path in config.get("wake_word", {}).get("model_paths", [])
    if not Path(path).exists()
]
if missing:
    raise SystemExit(f"Missing wake-word model: {missing[0]}")
print("Wake-word model files found")
PY

echo
echo "Setup complete."
echo "Run: ./run.sh"
