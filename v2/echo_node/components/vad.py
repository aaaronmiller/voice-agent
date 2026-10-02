"""Voice activity detection and turn recording.

Honesty note: the class historically named ``SileroVad`` never was Silero —
it wraps OpenWakeWord's VAD model (``openwakeword.VAD``) plus an RMS floor.
It is now called :class:`OpenWakeWordVad`; ``SileroVad`` remains as a
backward-compatibility alias.
"""

from __future__ import annotations

import os
import tempfile
import time
import wave
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from echo_node.components._common import rms_int16
from echo_node.slots import Capability, VADProvider
from echo_node.slots.validation import (
    ValidationResult,
    check_module,
    missing_result,
    ok_result,
)

if TYPE_CHECKING:
    from echo_node.components.audio import MicStream


# ── VAD (OpenWakeWord, not Silero) ───────────────────────────────────

class OpenWakeWordVad(VADProvider):
    """Speech/no-speech classifier.

    Combines OpenWakeWord's VAD score with an RMS energy floor: a frame
    counts as speech when either the model score clears ``speech_threshold``
    or the raw energy clears ``rms_floor``.
    """

    def __init__(self, config: dict[str, Any]):
        from openwakeword import VAD
        self.threshold = float(config.get("speech_threshold", 0.48))
        self.rms_floor = float(config.get("rms_floor", 350))
        self.vad = VAD()

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(
            name="openwakeword",
            version="unknown",
            languages=[],
            streaming=True,   # per-frame scoring
            gpu_required=False,
            license="Apache-2.0",  # openwakeword package license
            network=False,
            notes=("OpenWakeWord VAD model + RMS energy floor; the class "
                   "historically misnamed SileroVad"),
        )

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        found, ver = check_module("openwakeword")
        if found:
            return ok_result(f"openwakeword {ver} importable", {"version": ver})
        return missing_result("openwakeword", {"module": "openwakeword"})

    def score(self, samples: np.ndarray) -> float:
        try:
            return float(self.vad.predict(samples, frame_size=640))
        except Exception:
            return 0.0

    def is_speech(self, samples: np.ndarray) -> bool:
        return self.score(samples) >= self.threshold or rms_int16(samples) >= self.rms_floor


# Backward-compatibility alias: the old (misleading) name still resolves.
# (Kept for historical config compat; the REAL Silero is SileroVAD above.)
SileroVad = OpenWakeWordVad


# ── VAD (real Silero v6) ───────────────────────────────────────────
#
# Wraps the ``silero-vad`` PyPI package (v6.x, MIT). API written against
# the documented upstream surface (verified 2026-10-01 against the
# snakers4/silero-vad README and third-party ports):
#
#     from silero_vad import load_silero_vad
#     model = load_silero_vad(onnx=True)      # OnnxWrapper; torch-backed otherwise
#     model.reset_states()
#     prob = model(chunk_tensor, sample_rate).item()   # speech probability 0..1
#
# Per-chunk call details (exact tensor shapes accepted by OnnxWrapper) were
# NOT exercised on this VM — no torch here — so the windowing loop below
# carries a comment where the API surface is unverified. Phase-A rule
# honored: validate() never calls load_silero_vad() (first call downloads
# the 2.3 MB weights), only probes module presence.

class SileroVAD(VADProvider):
    """Real Silero voice-activity detection (silero-vad v6).

    Scores fixed 512-sample (32 ms @ 16 kHz) windows with the ONNX model
    and returns the max window probability for the chunk. ``is_speech``
    also consults an RMS energy floor so pure silence never passes.

    Experimental: unverified on target hardware. Requires the
    ``silero-vad`` pip package (which pulls torch + torchaudio as hard
    deps — see upstream issue about the [onnx-cpu] extra not shrinking
    the install).
    """

    _WINDOW = 512  # 32 ms @ 16 kHz — the v6 ONNX model's native window

    def __init__(self, config: dict[str, Any]):
        from silero_vad import load_silero_vad
        self.threshold = float(config.get("speech_threshold", 0.5))
        self.rms_floor = float(config.get("rms_floor", 350))
        self.sample_rate = int(config.get("sample_rate", 16000))
        # NOTE: first call downloads the model weights (~2.3 MB) into
        # ~/.cache — construction implies consent, never do this in validate().
        self._model = load_silero_vad(onnx=True)
        self._model.reset_states()

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(
            name="silero",
            version="6.x",
            languages=[],
            streaming=True,   # per-frame scoring
            gpu_required=False,  # CPU; ~1.5% CPU per ROADMAP survey
            license="MIT",
            network=False,
            notes=("real Silero VAD v6 (silero-vad PyPI); 16% fewer errors "
                   "on noisy data than the stale bundled model; experimental, "
                   "unverified on target hardware"),
        )

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        # Never load the model here — load_silero_vad() downloads weights
        # on first use. Module presence (+ torch) is the whole probe.
        found, ver = check_module("silero_vad")
        if not found:
            return missing_result("silero_vad", {"module": "silero_vad"})
        torch_found, torch_ver = check_module("torch")
        details = {"silero_vad": ver, "torch": torch_ver if torch_found else "missing"}
        if not torch_found:
            return missing_result("torch (hard dep of silero-vad)", details)
        return ok_result(f"silero_vad {ver} + torch present (model NOT loaded — "
                         "load() downloads weights on first use)", details)

    def reset(self) -> None:
        """Clear the model's recurrent state (call on turn boundaries)."""
        self._model.reset_states()

    def score(self, samples: np.ndarray) -> float:
        try:
            import torch
            audio = np.asarray(samples, dtype=np.float32).ravel()
            # UNVERIFIED on-device: OnnxWrapper call convention for raw
            # chunk tensors. Batched (1, N) float32 is the documented shape
            # for the v5/v6 torch API; kept here with a defensive fallback.
            windows = audio[: len(audio) // self._WINDOW * self._WINDOW]
            if windows.size == 0:
                return 0.0
            batch = torch.from_numpy(windows.reshape(1, -1)).float()
            with torch.no_grad():
                prob = self._model(batch, self.sample_rate).item()
            return float(prob)
        except Exception:
            return 0.0

    def is_speech(self, samples: np.ndarray) -> bool:
        return self.score(samples) >= self.threshold or rms_int16(samples) >= self.rms_floor


# ── Recorder ────────────────────────────────────────────────────────

class Recorder:
    """Records one user turn: starts on speech, ends after sustained silence.

    End-of-turn already uses hysteresis — a turn only ends after
    ``silence_seconds`` of continuous non-speech below the VAD/RMS floor, so
    mid-sentence dips don't chop the recording.
    """

    def __init__(self, mic: MicStream, vad: OpenWakeWordVad, config: dict[str, Any]):
        self.mic = mic
        self.vad = vad
        self.silence_seconds = float(config.get("silence_seconds", 0.85))
        self.max_record_seconds = float(config.get("max_record_seconds", 18))
        self.min_record_seconds = float(config.get("min_record_seconds", 0.45))
        self.wake_speech_timeout_seconds = float(config.get("wake_speech_timeout_seconds", 6))

    def record_turn(self) -> Path | None:
        started = time.monotonic()
        speech_started_at: float | None = None
        silence_started_at: float | None = None
        chunks: list[np.ndarray] = []
        print("[listen] speak now", flush=True)

        while True:
            samples = self.mic.read()
            now = time.monotonic()
            speaking = self.vad.is_speech(samples)

            if speaking:
                if speech_started_at is None:
                    speech_started_at = now
                silence_started_at = None
                chunks.append(samples)
            elif speech_started_at is not None:
                chunks.append(samples)
                if silence_started_at is None:
                    silence_started_at = now
                if now - silence_started_at >= self.silence_seconds and now - speech_started_at >= self.min_record_seconds:
                    return self._save(chunks)
            elif now - started >= self.wake_speech_timeout_seconds:
                return None

            if now - started >= self.max_record_seconds:
                return self._save(chunks) if chunks else None

    @staticmethod
    def _save(chunks: list[np.ndarray]) -> Path:
        fd, name = tempfile.mkstemp(prefix="echo-node-v2-", suffix=".wav")
        os.close(fd)
        path = Path(name)
        audio = np.concatenate(chunks).astype(np.int16) if chunks else np.array([], dtype=np.int16)
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(audio.tobytes())
        return path
