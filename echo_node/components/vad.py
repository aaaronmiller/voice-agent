"""
Echo-Node VAD Components — Silero VAD, voice recording.
"""

from __future__ import annotations

import os
import tempfile
import time
import wave
from pathlib import Path
from typing import Any

import numpy as np


class SileroVad:
    def __init__(self, config: dict[str, Any]):
        from openwakeword import VAD
        self.threshold = float(config.get("speech_threshold", 0.48))
        self.rms_floor = float(config.get("rms_floor", 350))
        self.vad = VAD()

    def score(self, samples: np.ndarray) -> float:
        try:
            return float(self.vad.predict(samples, frame_size=640))
        except Exception:
            return 0.0

    def is_speech(self, samples: np.ndarray) -> bool:
        return self.score(samples) >= self.threshold or rms_int16(samples) >= self.rms_floor


# ── Recorder ────────────────────────────────────────────────────────

class Recorder:
    def __init__(self, mic: MicStream, vad: SileroVad, config: dict[str, Any]):
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


# ── STT backends ────────────────────────────────────────────────────