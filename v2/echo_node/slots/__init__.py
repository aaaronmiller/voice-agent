"""Per-slot plugin interfaces for Echo-Node v2 (Phase A of ROADMAP.md).

Every swappable pipeline component implements one of the ABCs below:

  SlotType.WAKE_WORD    → WakeWordProvider  (detect wake phrase in mic audio)
  SlotType.VAD          → VADProvider       (speech / no-speech classification)
  SlotType.STT          → STTProvider       (speech-to-text)
  SlotType.TTS          → TTSProvider       (text-to-speech → WAV)
  SlotType.AGENT_BACKEND→ AgentBackend       (response generation; the ABC lives
                             in echo_node.backends to avoid an import cycle —
                             it IS the slot contract for this slot)
  SlotType.AVATAR       → AvatarRenderer    (lip-sync / talking-head visuals)
  SlotType.AUDIO_IO     → AudioIO           (mic capture)
  SlotType.BARGE_IN     → BargeInPolicy     (interruption decision policy)

Each provider class also exposes:

  capabilities() -> Capability   classmethod describing the provider
  validate(config=None) -> ValidationResult   classmethod running a real,
      graceful probe (never downloads models, never raises — returns an
      honest "missing X" result instead).

The central registry lives in echo_node.slots.registry. Registration is
explicit in-code (register_builtin()); entry-points can be added later.
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from echo_node.slots.validation import ValidationResult


# ── Slot types ──────────────────────────────────────────────────────

class SlotType(enum.Enum):
    WAKE_WORD = "wake_word"
    VAD = "vad"
    STT = "stt"
    TTS = "tts"
    AGENT_BACKEND = "agent_backend"
    AVATAR = "avatar"
    AUDIO_IO = "audio_io"
    BARGE_IN = "barge_in"


# ── Capability descriptor ───────────────────────────────────────────

@dataclass
class Capability:
    """What a provider offers / requires. Unknowns stay "unknown"."""
    name: str
    version: str = "unknown"
    languages: list[str] = field(default_factory=list)
    streaming: bool = False
    vram_gb: float | None = None
    gpu_required: bool = False
    license: str = "unknown"
    network: bool = False
    notes: str = ""


# ── Slot ABCs ───────────────────────────────────────────────────────
#
# Abstract methods mirror exactly what the pipeline already calls —
# no new call patterns are invented here.

class WakeWordProvider(ABC):
    """Detect a wake phrase in a mic chunk."""

    @abstractmethod
    def detect(self, samples: np.ndarray) -> tuple[bool, str, float]:
        """Return (detected, phrase_name, score)."""
        ...

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(name=cls.__name__)

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        return ValidationResult(False, "no validator implemented", {})


class VADProvider(ABC):
    """Speech / no-speech classifier over a mic chunk."""

    @abstractmethod
    def score(self, samples: np.ndarray) -> float:
        ...

    @abstractmethod
    def is_speech(self, samples: np.ndarray) -> bool:
        ...

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(name=cls.__name__)

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        return ValidationResult(False, "no validator implemented", {})


class STTProvider(ABC):
    """Speech-to-text: transcribe a WAV file to text."""

    @abstractmethod
    def load(self) -> None:
        ...

    @abstractmethod
    def unload(self) -> None:
        ...

    @abstractmethod
    def transcribe(self, wav_path: Path) -> str:
        ...

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(name=cls.__name__)

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        return ValidationResult(False, "no validator implemented", {})


class TTSProvider(ABC):
    """Text-to-speech: synthesize text to a WAV file."""

    @abstractmethod
    def load(self) -> None:
        ...

    @abstractmethod
    def unload(self) -> None:
        ...

    @abstractmethod
    def warm(self) -> None:
        ...

    @abstractmethod
    def synthesize_to_wav(self, text: str, path: Path) -> Path:
        ...

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(name=cls.__name__)

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        return ValidationResult(False, "no validator implemented", {})


# NOTE: the AGENT_BACKEND slot ABC is echo_node.backends.AgentBackend.
# It is defined there (not here) to avoid an import cycle; the registry
# treats it as the contract for SlotType.AGENT_BACKEND.


class AvatarRenderer(ABC):
    """Visual avatar: lip-sync / talking-head driven by TTS audio."""

    @abstractmethod
    def preload(self, wav_path: Path) -> bool:
        """Prepare visuals for *wav_path*; return True if visuals will play."""
        ...

    @abstractmethod
    def play(self) -> None:
        ...

    @abstractmethod
    def stop(self) -> None:
        ...

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(name=cls.__name__)

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        return ValidationResult(False, "no validator implemented", {})


class AudioIO(ABC):
    """Microphone capture."""

    @abstractmethod
    def open(self) -> None:
        ...

    @abstractmethod
    def read(self) -> np.ndarray:
        ...

    @abstractmethod
    def close(self) -> None:
        ...

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(name=cls.__name__)

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        return ValidationResult(False, "no validator implemented", {})


class BargeInPolicy(ABC):
    """Decide whether the user is interrupting TTS playback."""

    def __init__(self, vad: VADProvider, config: dict[str, Any]):
        self.vad = vad
        self.config = dict(config)

    @abstractmethod
    def is_bargein_speech(
        self,
        samples: np.ndarray,
        started: float,
        grace_window: float,
        original_threshold: float,
        original_rms: float,
    ) -> bool:
        """True when *samples* look like real user speech during playback."""
        ...

    @abstractmethod
    def check(
        self,
        is_speech: bool,
        speech_started: float | None,
        silence_started: float | None,
        now: float,
    ) -> tuple[bool, float | None, float | None]:
        """Debounce + hysteresis state machine.

        Returns (triggered, speech_started, silence_started).
        """
        ...

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(name=cls.__name__)

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        return ValidationResult(False, "no validator implemented", {})


__all__ = [
    "SlotType",
    "Capability",
    "WakeWordProvider",
    "VADProvider",
    "STTProvider",
    "TTSProvider",
    "AvatarRenderer",
    "AudioIO",
    "BargeInPolicy",
    "ValidationResult",
]
