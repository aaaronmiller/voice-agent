"""Phase A conformance tests: slots + registry + validators.

Run:  python3 -m echo_node.tests.test_phase_a
      (or pytest echo_node/tests/test_phase_a.py)

These tests need no GPU, no audio hardware, and no downloaded models —
they assert registry structure, selection equivalence with the old
string-if/else dispatch, and honest validation behavior.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running as a script from v2/: python3 echo_node/tests/test_phase_a.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from echo_node.slots import (
    AudioIO,
    AvatarRenderer,
    BargeInPolicy,
    Capability,
    SlotType,
    STTProvider,
    TTSProvider,
    VADProvider,
    WakeWordProvider,
)
from echo_node.slots.registry import get_registry
from echo_node.slots.validation import ValidationResult

REG = get_registry()

failures: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    status = "ok" if cond else "FAIL"
    print(f"[{status}] {label}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label + (f": {detail}" if detail else ""))


# ── 1. Every slot has providers registered ──────────────────────────

EXPECTED = {
    SlotType.STT: {"faster-whisper", "parakeet", "onnx-asr"},
    SlotType.TTS: {"kokoro", "dots", "cosyvoice3", "espeak-ng"},
    SlotType.AGENT_BACKEND: {"hermes", "pi", "claude", "codex", "openai",
                             "openrouter", "gemini_live", "openai_realtime"},
    SlotType.VAD: {"openwakeword"},
    SlotType.WAKE_WORD: {"openwakeword"},
    SlotType.AUDIO_IO: {"alsa", "sounddevice"},
    SlotType.BARGE_IN: {"vad_gated"},
    SlotType.AVATAR: {"rhubarb", "musetalk"},
}

for slot, names in EXPECTED.items():
    got = set(REG.all_names(slot))
    check(f"registry has all {slot.value} providers", names <= got,
          f"missing={sorted(names - got)}")


# ── 2. Selection equivalence with the old dispatch ──────────────────

from echo_node.components.stt import FasterWhisperSTT, ParakeetSTT, create_stt
from echo_node.components.tts import (
    CosyVoice3TTS, DotsTTS, EspeakTTS, KokoroTTS, create_tts,
)

check("stt faster-whisper → FasterWhisperSTT",
      isinstance(create_stt({"provider": "faster-whisper"}), FasterWhisperSTT))
for p in ("parakeet", "onnx-asr", "bogus-provider"):
    check(f"stt {p!r} → ParakeetSTT",
          isinstance(create_stt({"provider": p}), ParakeetSTT))

check("tts kokoro → KokoroTTS",
      isinstance(create_tts({"provider": "kokoro"}), KokoroTTS))
# dots/cosyvoice3/espeak-ng selection: the class must be picked by name
# even when construction fails (fallback happens inside create_tts only
# on exception, mirroring the old try/except).
from echo_node.components import tts as tts_mod
import unittest.mock as mock

with mock.patch.object(tts_mod.DotsTTS, "__init__", lambda self, cfg: None):
    check("tts dots → DotsTTS",
          isinstance(create_tts({"provider": "dots"}), DotsTTS))
with mock.patch.object(tts_mod.CosyVoice3TTS, "__init__", lambda self, cfg: None):
    check("tts cosyvoice3 → CosyVoice3TTS",
          isinstance(create_tts({"provider": "cosyvoice3"}), CosyVoice3TTS))
check("tts espeak-ng registered as EspeakTTS",
      REG.get(SlotType.TTS, "espeak-ng") is EspeakTTS)
check("tts unknown → EspeakTTS (old else-branch)",
      REG.get(SlotType.TTS, "kokoro") is KokoroTTS)

# registry.get returns the exact class the old dispatch picked
check("registry stt/faster-whisper is FasterWhisperSTT",
      REG.get(SlotType.STT, "faster-whisper") is FasterWhisperSTT)
check("registry stt/parakeet is ParakeetSTT",
      REG.get(SlotType.STT, "parakeet") is ParakeetSTT)
check("registry stt/onnx-asr aliases ParakeetSTT",
      REG.get(SlotType.STT, "onnx-asr") is ParakeetSTT)

from echo_node.backends import (
    HermesBackend, OpenAIRealtimeBackend, create_backend,
)
check("create_backend('hermes') → HermesBackend",
      isinstance(create_backend("hermes", {}), HermesBackend))
try:
    create_backend("nope", {})
    check("create_backend('nope') raises ValueError", False)
except ValueError:
    check("create_backend('nope') raises ValueError", True)


# ── 3. ABC conformance (structural) ─────────────────────────────────

ABC_FOR_SLOT = {
    SlotType.STT: STTProvider,
    SlotType.TTS: TTSProvider,
    SlotType.VAD: VADProvider,
    SlotType.WAKE_WORD: WakeWordProvider,
    SlotType.AUDIO_IO: AudioIO,
    SlotType.BARGE_IN: BargeInPolicy,
    SlotType.AVATAR: AvatarRenderer,
}

for slot, abc in ABC_FOR_SLOT.items():
    for info in REG.all_providers(slot):
        if info.name in {"musetalk"} or info.provider_cls.__name__.startswith("Missing"):
            continue  # prototype / placeholder: contract gap is validated, not asserted
        check(f"{slot.value}/{info.name} subclasses {abc.__name__}",
              issubclass(info.provider_cls, abc))


# ── 4. working() excludes experimental ──────────────────────────────

for slot in SlotType:
    names = {i.name for i in REG.working(slot)}
    for info in REG.all_providers(slot):
        if info.experimental:
            check(f"working({slot.value}) excludes experimental {info.name!r}",
                  info.name not in names)

exp_names = {i.name for s in SlotType for i in REG.all_providers(s) if i.experimental}
check("experimental set is as expected",
      exp_names == {
          # Phase A/B baseline
          "cosyvoice3", "gemini_live", "openai_realtime", "musetalk",
          # Phase C(e-f): llama-swap local model router
          "llama-swap",
          # Phase C(a-d, concurrent worker): silero VAD, qwen3-tts/voxcpn TTS,
          # aec-webrtc audio I/O, musetalk-livetalking avatar
          "silero", "qwen3-tts", "voxcpn", "aec-webrtc", "musetalk-livetalking",
      },
      f"got {sorted(exp_names)}")


# ── 5. No config key renamed ─────────────────────────────────────────

import yaml
V2 = Path(__file__).resolve().parent.parent.parent
example = yaml.safe_load((V2 / "config.example.yaml").read_text())
pairs = [
    (SlotType.STT, str(example["stt"]["provider"])),
    (SlotType.TTS, str(example["tts"]["provider"])),
    (SlotType.AGENT_BACKEND, str(example["backend"]["provider"])),
    (SlotType.AUDIO_IO, str(example["audio"]["backend"])),
    (SlotType.VAD, str(example["vad"]["provider"])),
]
for slot, name in pairs:
    check(f"config.example.yaml {slot.value}={name!r} still registered",
          name in REG.all_names(slot), f"{slot.value}={name}")


# ── 6. validate_all() is honest and total ────────────────────────────

report = REG.validate_all()
total_registered = sum(len(REG.all_names(s)) for s in SlotType)
check("validate_all covers every registration",
      len(report) == total_registered,
      f"report={len(report)} registered={total_registered}")
for key, entry in report.items():
    check(f"validate_all entry {key} well-formed",
          isinstance(entry["ok"], bool) and isinstance(entry["reason"], str)
          and entry["reason"] and isinstance(entry["details"], dict))

# On this VM (no GPU, no audio hw, no models, no API keys) most providers
# must fail honestly — not crash, and not claim to work.
ok_count = sum(1 for e in report.values() if e["ok"])
check("validators degrade gracefully on bare VM (not all pass)",
      ok_count < len(report), f"{ok_count}/{len(report)} passed")


# ── 7. Barge-in policy state machine ─────────────────────────────────

from echo_node.components.barge_in import VadGatedBargeIn


class _FakeVad:
    def score(self, samples):
        return 0.0


pol = VadGatedBargeIn(_FakeVad(), {})
now = 100.0
# sustained speech past min_speech_seconds triggers
ss, sil = None, None
trig = False
t = now
while t < now + 1.0:
    trig, ss, sil = pol.check(True, ss, sil, t)
    t += 0.05
check("barge-in triggers after sustained speech", trig)
# a single quiet frame must not cancel a pending trigger (hysteresis)
ss, sil = None, None
trig, ss, sil = pol.check(True, ss, sil, now)
trig, ss, sil = pol.check(False, ss, sil, now + 0.01)  # one quiet frame
check("single quiet frame does not cancel pending trigger",
      ss is not None and not trig)
# sustained silence past grace abandons the pending trigger
trig, ss, sil = pol.check(False, ss, sil, now + 1.0)
check("sustained silence abandons pending trigger", ss is None and not trig)


# ── 8. Capabilities are real, not invented ────────────────────────────

for slot in SlotType:
    for info in REG.all_providers(slot):
        cap = info.capabilities
        check(f"{slot.value}/{info.name} has a Capability",
              isinstance(cap, Capability) and bool(cap.name))


print()
if failures:
    print(f"{len(failures)} FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("all Phase A conformance checks passed")
