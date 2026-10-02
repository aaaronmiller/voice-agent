"""AEC far-end wiring (Phase C follow-up).

Verifies, with no audio hardware / GPU / PyQt6:
- ``create_audio_io`` dispatch: default → MicStream, explicit provider →
  registry class, unknown → MicStream fallback.
- ``read_wav_mono16``: PCM16 passthrough, stereo→mono, 8-bit unsigned,
  sample-rate conversion, junk input → clear error.
- ``InterruptibleSpeaker._feed_far_end``: no-op when the callback is None,
  feeds converted PCM when set, never raises on a bad WAV, and runs at
  the top of ``_play_wav`` (before any backend playback attempt).

Runs as a script: ``python3 -m echo_node.tests.test_aec_wiring`` from ``v2/``.
"""

from __future__ import annotations

import os
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASSED: list[str] = []
FAILED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    (PASSED if ok else FAILED).append(label)
    print(f"[{'ok' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""),
          flush=True)


from echo_node.components.aec import AecAudioIO, read_wav_mono16  # noqa: E402
from echo_node.components.audio import (  # noqa: E402
    AudioConfig,
    InterruptibleSpeaker,
    MicStream,
    create_audio_io,
)


def _write_wav(path: Path, data: np.ndarray, sr: int,
               sampwidth: int = 2, nchan: int = 1) -> None:
    """Write raw PCM with the stdlib wave module (no soundfile needed)."""
    if nchan > 1:
        assert data.ndim == 2 and data.shape[1] == nchan
        frames = data.reshape(-1)
    else:
        frames = np.asarray(data).ravel()
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(nchan)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sr)
        if sampwidth == 1:
            wf.writeframes((np.clip(frames, -1, 1) * 127 + 128)
                           .astype(np.uint8).tobytes())
        else:
            wf.writeframes((np.clip(frames, -1, 1) * 32767)
                           .astype(np.int16).tobytes())


TMP = Path(tempfile.mkdtemp(prefix="aec-test-"))

# ── read_wav_mono16 ──────────────────────────────────────────────────

t = np.linspace(0, 0.5, 8000, endpoint=False)
sine16 = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
p1 = TMP / "mono16.wav"
_write_wav(p1, sine16, 16000)
out = read_wav_mono16(p1, 16000)
check("mono16 passthrough: dtype/shape",
      out.dtype == np.int16 and out.shape == (8000,))
check("mono16 passthrough: values",
      np.abs(out.astype(np.float32) / 32767 - sine16).max() < 0.002)

# Stereo 24 kHz → mono 16 kHz.
sine24 = (0.5 * np.sin(2 * np.pi * 440 * np.linspace(0, 0.5, 12000,
                                                   endpoint=False))).astype(np.float32)
p2 = TMP / "stereo24.wav"
_write_wav(p2, np.stack([sine24, sine24], axis=1), 24000, nchan=2)
out2 = read_wav_mono16(p2, 16000)
check("stereo24→mono16: length", out2.shape == (8000,), str(out2.shape))
check("stereo24→mono16: content sane",
      np.abs(out2.astype(np.float32)).max() > 10000)

# 8-bit unsigned mono.
p3 = TMP / "u8.wav"
_write_wav(p3, sine16, 16000, sampwidth=1)
out3 = read_wav_mono16(p3, 16000)
check("8-bit unsigned converts",
      out3.dtype == np.int16 and np.abs(out3.astype(np.float32)).max() > 10000)

# Junk input → clear error, not a traceback mystery.
pj = TMP / "junk.wav"
pj.write_bytes(b"this is not a wav file at all, just text")
try:
    read_wav_mono16(pj, 16000)
    check("junk wav raises ValueError", False)
except ValueError as exc:
    check("junk wav raises ValueError", True, str(exc)[:60])
except Exception as exc:  # noqa: BLE001
    check("junk wav raises ValueError", False, f"wrong type: {type(exc)}")

# ── create_audio_io dispatch ─────────────────────────────────────────

m0 = create_audio_io({})
check("default → MicStream", isinstance(m0, MicStream))
check("default honours backend=alsa", m0.config.backend == "alsa")

m1 = create_audio_io({"backend": "sounddevice", "sample_rate": 16000,
                      "chunk_size": 1280})
check("backend sounddevice → MicStream", isinstance(m1, MicStream))

m2 = create_audio_io({"backend": "alsa", "sample_rate": 16000,
                      "chunk_size": 1280, "provider": "aec-webrtc"})
check("provider aec-webrtc → AecAudioIO", isinstance(m2, AecAudioIO))

m3 = create_audio_io({"backend": "alsa", "provider": "does-not-exist"})
check("unknown provider → MicStream fallback", isinstance(m3, MicStream))

# AudioConfig tolerates the new optional key (orchestrator does
# AudioConfig(**config["audio"]) even when provider: is present).
ac = AudioConfig(**{"backend": "alsa", "sample_rate": 16000,
                    "chunk_size": 1280, "provider": "aec-webrtc"})
check("AudioConfig accepts provider key", ac.provider == "aec-webrtc")
ac2 = AudioConfig(backend="alsa", sample_rate=16000, chunk_size=1280)
check("AudioConfig provider defaults to None", ac2.provider is None)

# ── speaker far-end tap ──────────────────────────────────────────────

def _bare_speaker(**kw):
    sp = InterruptibleSpeaker.__new__(InterruptibleSpeaker)
    sp.audio = AudioConfig(backend="alsa", sample_rate=16000, chunk_size=1280)
    sp.far_end_callback = kw.get("far_end_callback")
    return sp

# No callback → no-op, no error, even on a missing file.
sp0 = _bare_speaker(far_end_callback=None)
try:
    sp0._feed_far_end(TMP / "does-not-exist.wav")
    check("no callback → silent no-op", True)
except Exception as exc:  # noqa: BLE001
    check("no callback → silent no-op", False, str(exc))

# Callback receives converted PCM.
got: list[np.ndarray] = []
sp1 = _bare_speaker(far_end_callback=got.append)
sp1._feed_far_end(p2)  # stereo 24 kHz file
check("callback invoked once", len(got) == 1)
if got:
    check("callback got int16 mono @16000",
          got[0].dtype == np.int16 and got[0].shape == (8000,))

# Corrupt WAV → no raise, callback not called.
sp2 = _bare_speaker(far_end_callback=got.append)
n_before = len(got)
try:
    sp2._feed_far_end(pj)
    check("corrupt wav → no raise", len(got) == n_before)
except Exception as exc:  # noqa: BLE001
    check("corrupt wav → no raise", False, str(exc))

# Tap placement: _play_wav feeds far-end BEFORE attempting playback
# (aplay is absent on this VM, so playback raises — the tap must still
# have fired).
sp3 = _bare_speaker(far_end_callback=got.append)
n_before = len(got)
try:
    sp3._play_wav(p1, None)
    check("_play_wav tap fired before playback attempt", False,
          "expected RuntimeError from missing aplay")
except RuntimeError as exc:
    check("_play_wav tap fired before playback attempt",
          len(got) == n_before + 1, str(exc)[:40])
except Exception as exc:  # noqa: BLE001
    check("_play_wav tap fired before playback attempt", False,
          f"wrong error: {type(exc).__name__}: {exc}")

# Orchestrator wiring expression: only providers exposing feed_far_end
# get a callback (MicStream has none → None; AecAudioIO has it).
check("MicStream exposes no feed_far_end",
      getattr(MicStream, "feed_far_end", None) is None)
check("AecAudioIO exposes feed_far_end",
      callable(getattr(AecAudioIO, "feed_far_end", None)))

print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
sys.exit(1 if FAILED else 0)
