#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

source "$ROOT/env.sh"
echo_node_export_nvidia_libs "$ROOT"

echo "Echo-Node v2 checks"
echo "==================="

failures=0
check() {
  local label="$1"
  shift
  if "$@" >/tmp/echo-node-v2-check.out 2>/tmp/echo-node-v2-check.err; then
    echo "✓ $label"
  else
    echo "✗ $label"
    cat /tmp/echo-node-v2-check.err
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

check_file "config.yaml" config.yaml
check_file "assistant_v2.py" assistant_v2.py
check_file "Kokoro model" models/kokoro/kokoro-v1.0.onnx
check_file "Kokoro voices" models/kokoro/voices-v1.0.bin
check "Python venv" test -x .venv/bin/python
check "arecord" command -v arecord
check "aplay" command -v aplay
check "espeak-ng" command -v espeak-ng
check "Imports" .venv/bin/python -c "import numpy, yaml, requests, soundfile, onnx_asr; from openwakeword import VAD; from openwakeword.model import Model; from kokoro_onnx import Kokoro"
check "ONNX Runtime providers" .venv/bin/python - <<'PY'
import onnxruntime as ort
print(ort.get_available_providers())
PY
check "Syntax" .venv/bin/python -m py_compile assistant_v2.py
check "Wake + VAD initialize" .venv/bin/python - <<'PY'
import yaml
from assistant_v2 import WakeDetector, SileroVad
with open("config.yaml", "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)
WakeDetector(cfg["wake_word"])
SileroVad(cfg["vad"])
PY
check "Parakeet v2 sample transcription" .venv/bin/python - <<'PY'
from pathlib import Path
from assistant_v2 import ParakeetSTT
sample = Path("/home/misscheta/.cache/openwhispr/parakeet-models/parakeet-tdt-0.6b-v3/test_wavs/en.wav")
text = ParakeetSTT({"model_name": "nemo-parakeet-tdt-0.6b-v2", "quantization": "int8"}).transcribe(sample)
if "Ask not what your country can do for you" not in text:
    raise SystemExit(text)
PY
check "Kokoro WAV synthesis" .venv/bin/python - <<'PY'
from pathlib import Path
from assistant_v2 import KokoroTTS
tts = KokoroTTS({
    "model_path": "models/kokoro/kokoro-v1.0.onnx",
    "voices_path": "models/kokoro/voices-v1.0.bin",
    "voice": "af_heart",
    "speed": 1.0,
})
out = tts.synthesize_to_wav("Voice test.", Path("/tmp/echo-node-v2-kokoro.wav"))
if out.stat().st_size < 1000:
    raise SystemExit("empty wav")
PY

echo
if [[ "$failures" -gt 0 ]]; then
  echo "$failures check(s) failed."
  exit 1
fi
echo "All checks passed."
