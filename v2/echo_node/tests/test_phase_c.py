"""Phase C conformance: substitution providers (silero VAD, AEC, Qwen3-TTS,
VoxCPM TTS, LiveTalking MuseTalk harness).

Run:  python3 -m echo_node.tests.test_phase_c
      (or pytest echo_node/tests/test_phase_c.py)

Needs no GPU, no audio hardware, and no downloaded models — on this bare
VM every new provider's validator must report an honest "missing X"
without crashing and without downloading anything. Experimental gating
is verified via stubbed validate_fn (no real deps needed).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow running as a script from v2/: python3 echo_node/tests/test_phase_c.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import numpy as np

from echo_node.components.aec import AecAudioIO
from echo_node.components.tts import Qwen3TTS, VoxCPMTTS, create_tts
from echo_node.components.vad import SileroVAD
from echo_node.slots import (
    AudioIO,
    AvatarRenderer,
    Capability,
    SlotType,
    TTSProvider,
    VADProvider,
)
from echo_node.slots.registry import ProviderRegistry, register_builtin
from echo_node.slots.validation import ValidationResult, ok_result
from avatar_video.livetalking_musetalk import LiveTalkingMuseTalk

PASSED: list[str] = []
FAILED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    (PASSED if ok else FAILED).append(label)
    print(f"[{'ok' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail and not ok else ""),
          flush=True)


def _missing_ok(cls, label: str, *needles: str) -> None:
    """validate() must return an honest missing-result, never raise/download."""
    try:
        result = cls.validate()
    except Exception as exc:  # noqa: BLE001 — the point is it must not raise
        check(label, False, f"validator raised {type(exc).__name__}: {exc}")
        return
    is_vr = isinstance(result, ValidationResult)
    needles_ok = all(n in result.reason or n in str(result.details) for n in needles) \
        if is_vr else False
    check(label, is_vr and result.ok is False and needles_ok,
          f"got {result!r}" if not (is_vr and result.ok is False and needles_ok) else "")


# ── a. Silero v6 VAD ──────────────────────────────────────────────────

check("SileroVAD subclasses VADProvider", issubclass(SileroVAD, VADProvider))
check("SileroVAD implements score/is_speech",
      callable(SileroVAD.score) and callable(SileroVAD.is_speech))
cap = SileroVAD.capabilities()
check("SileroVAD.capabilities() is a Capability",
      isinstance(cap, Capability) and cap.name == "silero" and cap.license == "MIT")
_missing_ok(SileroVAD, "SileroVAD.validate() honest missing on bare VM", "silero_vad")
try:
    SileroVAD({})
    check("SileroVAD() without dep raises ImportError (honest)", False, "no error raised")
except ImportError:
    check("SileroVAD() without dep raises ImportError (honest)", True)
except Exception as exc:  # noqa: BLE001
    check("SileroVAD() without dep raises ImportError (honest)", False,
          f"raised {type(exc).__name__}")


# ── b. AEC ────────────────────────────────────────────────────────────

check("AecAudioIO subclasses AudioIO", issubclass(AecAudioIO, AudioIO))
check("AecAudioIO implements open/read/close",
      all(callable(getattr(AecAudioIO, m, None)) for m in ("open", "read", "close")))
check("AecAudioIO has feed_far_end hook", callable(getattr(AecAudioIO, "feed_far_end", None)))
cap = AecAudioIO.capabilities()
check("AecAudioIO.capabilities() is a Capability",
      isinstance(cap, Capability) and cap.name == "aec-webrtc")
_missing_ok(AecAudioIO, "AecAudioIO.validate() honest missing on bare VM", "pywebrtc_audio")

# Construction must not touch the binding; far-end buffer math is pure.
try:
    aec = AecAudioIO({"backend": "alsa", "sample_rate": 16000, "chunk_size": 1280})
    aec.feed_far_end(np.arange(100, dtype=np.int16))
    far = aec._take_far(160)
    check("AecAudioIO far-end buffer pads with zeros",
          far.shape == (160,) and far.dtype == np.int16 and (far[100:] == 0).all()
          and abs(aec.far_end_buffered_s) < 1e-9)
    check("AecAudioIO reports passthrough before open()", aec.passthrough)
except Exception as exc:  # noqa: BLE001
    check("AecAudioIO constructs + buffers far-end on bare VM", False, repr(exc)[:100])


# ── c. TTS tiers ──────────────────────────────────────────────────────

for cls, cname in ((Qwen3TTS, "qwen3-tts"), (VoxCPMTTS, "voxcpn")):
    check(f"{cls.__name__} subclasses TTSProvider", issubclass(cls, TTSProvider))
    cap = cls.capabilities()
    check(f"{cls.__name__}.capabilities() name={cname!r}",
          isinstance(cap, Capability) and cap.name == cname)
_missing_ok(Qwen3TTS, "Qwen3TTS.validate() honest missing on bare VM", "qwen_tts")
_missing_ok(VoxCPMTTS, "VoxCPMTTS.validate() honest missing on bare VM", "voxcpm")
for cls in (Qwen3TTS, VoxCPMTTS):
    try:
        cls({})
        check(f"{cls.__name__}() without dep raises ImportError (honest)", False,
              "no error raised")
    except ImportError:
        check(f"{cls.__name__}() without dep raises ImportError (honest)", True)
    except Exception as exc:  # noqa: BLE001
        check(f"{cls.__name__}() without dep raises ImportError (honest)", False,
              f"raised {type(exc).__name__}")


# ── d. LiveTalking harness ────────────────────────────────────────────

check("LiveTalkingMuseTalk subclasses AvatarRenderer",
      issubclass(LiveTalkingMuseTalk, AvatarRenderer))
check("LiveTalkingMuseTalk implements preload/play/stop",
      all(callable(getattr(LiveTalkingMuseTalk, m, None))
          for m in ("preload", "play", "stop")))
cap = LiveTalkingMuseTalk.capabilities()
check("LiveTalkingMuseTalk.capabilities() is a Capability",
      isinstance(cap, Capability) and cap.name == "musetalk-livetalking"
      and cap.gpu_required)
_missing_ok(LiveTalkingMuseTalk,
            "LiveTalkingMuseTalk.validate() honest missing on bare VM", "torch")

# Constructor + lifecycle must be safe without heavy deps.
try:
    harness = LiveTalkingMuseTalk({"photo_path": "/nonexistent/face.jpg"})
    check("LiveTalkingMuseTalk() constructs on bare VM", True)
    check("preload() returns False (not raise) when renderer can't load",
          harness.preload(Path("/nonexistent/x.wav")) is False)
    harness.play()   # no renderer → no-op, must not raise
    harness.stop()   # idempotent, must not raise
    check("play()/stop() safe without renderer", True)
except Exception as exc:  # noqa: BLE001
    check("LiveTalkingMuseTalk lifecycle safe on bare VM", False, repr(exc)[:100])


# ── Registry: registration + experimental gating ─────────────────────

_saved_env = os.environ.pop("ECHO_INCLUDE_EXPERIMENTAL", None)
try:
    reg = register_builtin()
    expected = [
        (SlotType.VAD, "silero"),
        (SlotType.TTS, "qwen3-tts"),
        (SlotType.TTS, "voxcpn"),
        (SlotType.AUDIO_IO, "aec-webrtc"),
        (SlotType.AVATAR, "musetalk-livetalking"),
    ]
    for slot, name in expected:
        try:
            info = reg.info(slot, name)
            check(f"registered {slot.value}/{name} experimental=True",
                  info.experimental is True)
        except KeyError:
            check(f"registered {slot.value}/{name} experimental=True", False,
                  "not registered")

    # Defaults unchanged.
    tts = create_tts({"provider": "kokoro"})
    check("default TTS selection unchanged (kokoro→KokoroTTS)",
          type(tts).__name__ == "KokoroTTS")
    # Historical fallback: unknown provider → espeak-ng. The espeak-ng
    # binary is absent on this VM, so mock shutil.which to exercise the
    # selection path (not the binary itself).
    import shutil as _shutil
    import unittest.mock as _mock
    with _mock.patch.object(_shutil, "which", lambda name: "/usr/bin/espeak-ng"):
        tts2 = create_tts({"provider": "bogus-provider"})
    check("unknown TTS provider still falls back to espeak-ng",
          type(tts2).__name__ == "EspeakTTS")
    check("registry resolves qwen3-tts class",
          reg.get(SlotType.TTS, "qwen3-tts") is Qwen3TTS)

    # Experimental gate: stub validators to ok, then check working().
    for slot, name in expected:
        info = reg.info(slot, name)
        orig_fn, orig_last = info.validate_fn, info.last_validation
        info.validate_fn = lambda cfg: ok_result("stubbed ok for gate test")
        info.last_validation = None
        try:
            names = [i.name for i in reg.working(slot)]
            gated_out = name not in names
            os.environ["ECHO_INCLUDE_EXPERIMENTAL"] = "1"
            names_in = [i.name for i in reg.working(slot)]
            gated_in = name in names_in
            check(f"{slot.value}/{name} gated without env, visible with it",
                  gated_out and gated_in,
                  f"out={gated_out} in={gated_in}")
        finally:
            del os.environ["ECHO_INCLUDE_EXPERIMENTAL"]
            info.validate_fn, info.last_validation = orig_fn, orig_last
finally:
    if _saved_env is not None:
        os.environ["ECHO_INCLUDE_EXPERIMENTAL"] = _saved_env


# ── summary ─────────────────────────────────────────────────────────────

print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
if FAILED:
    print("FAILED:", FAILED)
    sys.exit(1)
