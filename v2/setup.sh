#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "Echo-Node v2 setup"
echo "=================="

PYTHON_BIN=""
for candidate in python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
    then
      PYTHON_BIN="$candidate"
      break
    fi
  fi
done

if [[ -z "$PYTHON_BIN" ]]; then
  echo "ERROR: Python 3.11 or newer is required." >&2
  exit 1
fi

for tool in arecord aplay espeak-ng; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "ERROR: $tool is required." >&2
    exit 1
  fi
done

"$PYTHON_BIN" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

python - <<'PY'
from openwakeword.utils import download_models

download_models(model_names=["hey_jarvis"])
PY

mkdir -p models/kokoro
download() {
  local url="$1"
  local out="$2"
  if [[ -f "$out" ]]; then
    echo "Already present: $out"
    return
  fi
  echo "Downloading $out"
  curl -L "$url" -o "$out"
}

download "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx" "models/kokoro/kokoro-v1.0.onnx"
download "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin" "models/kokoro/voices-v1.0.bin"

if [[ ! -f config.yaml ]]; then
  cp config.example.yaml config.yaml
fi

echo
echo "Setup complete. Run ./test.sh, then ./run.sh"
