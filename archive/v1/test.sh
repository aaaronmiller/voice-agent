#!/usr/bin/env bash
set -euo pipefail

echo "Echo-Node Local Voice MVP test"
echo "=============================="

failures=0

check() {
  local label="$1"
  shift
  if "$@" >/tmp/voice-agent-check.out 2>/tmp/voice-agent-check.err; then
    echo "✓ $label"
  else
    echo "✗ $label"
    cat /tmp/voice-agent-check.err
    failures=$((failures + 1))
  fi
}

check_file() {
  local label="$1"
  local path="$2"
  if [[ -e "$path" ]]; then
    echo "✓ $label"
  else
    echo "✗ $label missing: $path"
    failures=$((failures + 1))
  fi
}

check_file "config.yaml" "config.yaml"
check_file "local_voice_assistant.py" "local_voice_assistant.py"
check_file "requirements.txt" "requirements.txt"

check "Python venv" test -x .venv/bin/python
check "espeak-ng" command -v espeak-ng
check "aplay" command -v aplay
check "arecord" command -v arecord
check "ollama CLI" command -v ollama

if [[ -x .venv/bin/python ]]; then
  check "Python imports" .venv/bin/python -c "import numpy, yaml, requests, onnx_asr; from openwakeword.model import Model"
  check "Assistant syntax" .venv/bin/python -m py_compile local_voice_assistant.py
  check "Wake detector initializes" .venv/bin/python - <<'PY'
from local_voice_assistant import WakeWordDetector

WakeWordDetector({
    "enabled": True,
    "sensitivity": 0.35,
    "model_paths": [
        "/home/misscheta/code/RealtimeSTT/tests/suh_man_tuh.onnx",
        "/home/misscheta/code/RealtimeSTT/tests/suh_mahn_thuh.onnx",
    ],
})
PY
fi

if [[ -f config.yaml && -x .venv/bin/python ]]; then
  check "Config wake-word models" .venv/bin/python - <<'PY'
from pathlib import Path
import yaml
config = yaml.safe_load(Path("config.yaml").read_text()) or {}
for model_path in config.get("wake_word", {}).get("model_paths", []):
    if not Path(model_path).exists():
        raise SystemExit(model_path)
PY
fi

if [[ -x .venv/bin/python && -f /home/misscheta/.cache/openwhispr/parakeet-models/parakeet-tdt-0.6b-v3/test_wavs/en.wav ]]; then
  check "Parakeet v2 sample transcription" .venv/bin/python - <<'PY'
from pathlib import Path
from local_voice_assistant import ParakeetSTT

sample = Path("/home/misscheta/.cache/openwhispr/parakeet-models/parakeet-tdt-0.6b-v3/test_wavs/en.wav")
text = ParakeetSTT({"model_name": "nemo-parakeet-tdt-0.6b-v2", "quantization": "int8"}).transcribe(sample)
if "Ask not what your country can do for you" not in text:
    raise SystemExit(text)
PY
fi

echo
if [[ "$failures" -gt 0 ]]; then
  echo "$failures check(s) failed."
  exit 1
fi

echo "All checks passed."
