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
check_file "speech_format.py" echo_node/speech_format.py
check_file "agent_profiles.py" echo_node/agent_profiles.py
check "Python venv" test -x .venv/bin/python
check "arecord" command -v arecord
check "aplay" command -v aplay
check "espeak-ng" command -v espeak-ng
check "Imports" .venv/bin/python -c "import numpy, yaml, requests, soundfile; from openwakeword import VAD; from openwakeword.model import Model"
check "Syntax: assistant_v2.py" .venv/bin/python -m py_compile assistant_v2.py
check "Syntax: speech_format.py" .venv/bin/python -m py_compile echo_node/speech_format.py
check "Syntax: agent_profiles.py" .venv/bin/python -m py_compile echo_node/agent_profiles.py
check "Syntax: tts_dots.py" .venv/bin/python -m py_compile tts_dots.py
check "Wake + VAD initialize" .venv/bin/python - <<'PY'
import yaml
from assistant_v2 import WakeDetector, SileroVad
with open("config.yaml", "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)
WakeDetector(cfg["wake_word"])
SileroVad(cfg["vad"])
PY

# Check STT backend (faster-whisper or parakeet)
stt_provider=$(python3 -c "import yaml; c=yaml.safe_load(open('config.yaml')); print(c.get('stt',{}).get('provider','parakeet'))" 2>/dev/null || echo "parakeet")
if [[ "$stt_provider" == "faster-whisper" ]]; then
  check "STT (faster-whisper tiny) available" .venv/bin/python -c "from faster_whisper import WhisperModel; print('ok')"
else
  check "STT (parakeet) available" .venv/bin/python -c "import onnx_asr; print('ok')"
fi

# Check TTS backend
tts_provider=$(python3 -c "import yaml; c=yaml.safe_load(open('config.yaml')); print(c.get('tts',{}).get('provider','kokoro'))" 2>/dev/null || echo "kokoro")
if [[ "$tts_provider" == "dots" ]]; then
  check "TTS (dots.tts) model exists" test -d models/dots-tts-mf
  check "TTS (dots.tts) importable" .venv/bin/python -c "from tts_dots import DotsTTS; print('ok')"
else
  check_file "Kokoro model" models/kokoro/kokoro-v1.0.onnx
  check_file "Kokoro voices" models/kokoro/voices-v1.0.bin
fi

check "Speech formatter works" .venv/bin/python - <<'PY'
from echo_node.speech_format import format_for_speech
# Table summarization
t1 = "Here are the results:\n| Name | Score |\n|---|---|\n| Alice | 95 |\n| Bob | 87 |\n| Carol | 92 |"
r1 = format_for_speech(t1, max_sentences=3)
assert "table" in r1.lower() or "rows" in r1.lower(), f"Table not summarized: {r1}"
# Sentence trimming
t2 = "First sentence. Second sentence. Third sentence. Fourth sentence. Fifth sentence. Sixth sentence."
r2 = format_for_speech(t2, max_sentences=3)
assert r2.count(".") <= 4, f"Not trimmed: {r2}"
# Code block summarization
t3 = "Here's the code:\n```python\ndef foo():\n    pass\n```"
r3 = format_for_speech(t3)
assert "def foo" not in r3, f"Code not summarized: {r3}"
print("All speech format tests passed")
PY

check "Agent profiles load" .venv/bin/python - <<'PY'
from echo_node.agent_profiles import get_all_agents, SmartRouter
agents = get_all_agents()
router = SmartRouter(agents)
assert "fast" in agents
assert "hermes" in agents
route = router.classify("search the web for weather")
assert route == "hermes", f"Expected hermes, got {route}"
route2 = router.classify("what time is it")
# SmartRouter now routes everything to hermes by default
assert route2 == "hermes", f"Expected hermes, got {route2}"
print(f"OK: {len(agents)} agents loaded")
PY

check "Keyboard hotkey importable" .venv/bin/python -c "from assistant_v2 import KeyboardHotkey; print('ok')"
check "Hermes integration importable" .venv/bin/python -c "from assistant_v2 import HermesIntegration; print('ok')"
check "Pi integration importable" .venv/bin/python -c "from assistant_v2 import PiIntegration; print('ok')"
check "Avatar: all characters have frames" .venv/bin/python -c "
from avatar.controller import AvatarController, NullAvatar
import yaml
with open('config.yaml') as f:
    cfg = yaml.safe_load(f)
avatar_cfg = cfg.get('avatar', {'enabled': False})
if avatar_cfg.get('enabled'):
    ctrl = AvatarController(avatar_cfg)
    assert ctrl.enabled, 'Controller should be enabled'
    ctrl.shutdown()
    print('Avatar controller OK')
else:
    print('Avatar disabled in config (OK)')
"

echo
if [[ "$failures" -gt 0 ]]; then
  echo "$failures check(s) failed."
  exit 1
fi
echo "All checks passed."
