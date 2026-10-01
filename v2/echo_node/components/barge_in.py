"""Barge-in (interruption) policies.

:class:`VadGatedBargeIn` is the policy that was previously implemented as
private methods on :class:`InterruptibleSpeaker`
(``_is_bargein_speech`` / ``_bargein_triggered``); the code is moved here
verbatim so the policy is a swappable slot provider. Behavior is
unchanged — the speaker now delegates to this class.

Design (2026 best practice, all config-driven via ``barge_in``):
  a) VAD-gated — playback is interrupted on sustained local speech onset,
     never by waiting hundreds of ms for an STT transcript.
  b) Elevated thresholds during playback — the VAD score and RMS thresholds
     are boosted while TTS is playing so the assistant's own speaker bleed
     doesn't interrupt it.
  c) Debounce + hysteresis — ``min_speech_seconds`` of sustained speech
     before triggering (kills door-slams/transients), and the pending
     trigger is only abandoned after ``bargein_end_grace_s`` of sustained
     silence so one quiet frame can't cancel a real interruption.
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np

from echo_node.components._common import rms_int16
from echo_node.slots import BargeInPolicy, Capability
from echo_node.slots.validation import (
    ValidationResult,
    check_module,
    ok_result,
)


class VadGatedBargeIn(BargeInPolicy):
    """VAD-gated interruption with playback threshold boosting."""

    def __init__(self, vad: Any, config: dict[str, Any]):
        super().__init__(vad, config)
        # Debounce: sustained speech required before a barge-in triggers.
        self.min_speech_seconds = float(config.get("min_speech_seconds", 0.22))
        self.min_playback_age_seconds = float(config.get("min_playback_age_seconds", 0.45))
        # Hysteresis: sustained silence required before a pending barge-in is
        # abandoned, so a single quiet frame can't cancel a real interruption.
        self.bargein_end_grace_s = float(config.get("bargein_end_grace_s", 0.12))
        # Barge-in boost: during active playback, multiply VAD threshold and RMS
        # floor so the assistant's own speaker bleed doesn't trigger false interrupts,
        # but a real human voice (loud, sustained) still gets through.
        self.playback_threshold_boost = float(config.get("playback_threshold_boost", 1.8))
        self.playback_rms_boost = float(config.get("playback_rms_boost", 2.0))
        self.playback_start_grace_s = float(config.get("playback_start_grace_s", 0.3))

    def is_bargein_speech(
        self,
        samples: np.ndarray,
        started: float,
        grace_window: float,
        original_threshold: float,
        original_rms: float,
    ) -> bool:
        """Enhanced speech detection for barge-in during playback.

        During playback the assistant's own voice bleeds into the mic. A single
        moderate reading (VAD *or* RMS) isn't enough to trigger — both must
        exceed the boosted thresholds (AND gate). This prevents the speaker
        bleed from falsely interrupting while still letting real human speech
        through (real speech is high in both dimensions).

        The first ``grace_window`` seconds use an even higher boost to survive
        the initial TTS burst without falsely triggering.
        """
        age = time.monotonic() - started
        if age < grace_window:
            extra = 1.5
        else:
            extra = 1.0

        boost = self.playback_threshold_boost * extra
        boosted_threshold = min(0.99, original_threshold * boost)

        rms_boost = self.playback_rms_boost * extra
        boosted_rms = int(original_rms * rms_boost)

        score = self.vad.score(samples)
        rms = rms_int16(samples)

        # AND gate: both VAD score AND RMS must exceed boosted thresholds.
        # TTS speaker bleed typically scores moderate on one axis but not both.
        # Real human speech scores high on both axes.
        return score >= boosted_threshold and rms >= boosted_rms

    def check(
        self,
        is_speech: bool,
        speech_started: float | None,
        silence_started: float | None,
        now: float,
    ) -> tuple[bool, float | None, float | None]:
        """Debounce + hysteresis state machine for one VAD reading.

        Returns (triggered, speech_started, silence_started).
        """
        if is_speech:
            if speech_started is None:
                speech_started = now
            silence_started = None
            if now - speech_started >= self.min_speech_seconds:
                return True, speech_started, silence_started
        elif speech_started is not None:
            # Hysteresis: only abandon the pending trigger after sustained
            # silence, so one quiet frame can't cancel a real interruption.
            if silence_started is None:
                silence_started = now
            elif now - silence_started >= self.bargein_end_grace_s:
                speech_started = None
                silence_started = None
        return False, speech_started, silence_started

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(
            name="vad_gated",
            version="1.0",
            languages=[],
            streaming=True,
            license="unknown",
            network=False,
            notes=("VAD-gated interruption with playback threshold boost, "
                   "debounce and hysteresis; pure-Python policy, needs a VAD instance"),
        )

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        # The policy itself is pure Python; it scores through a VAD
        # instance supplied at construction. Class-level probe: the VAD
        # stack it was built against must be importable.
        found, ver = check_module("openwakeword")
        if found:
            return ok_result(f"policy code present; openwakeword {ver} available for scoring",
                             {"openwakeword": ver})
        return ValidationResult(False, "missing openwakeword",
                                {"openwakeword": "not installed"})
