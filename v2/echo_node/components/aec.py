"""Acoustic echo cancellation (AEC) for full-duplex capture.

Honesty statement: **true full-duplex AEC can only be validated on real
hardware** — a VM with no mic, no speakers, and no acoustic path cannot
prove echo is removed. Everything below is wired to the real algorithms
and degrades gracefully (honest validator, passthrough when the binding
is absent), but the "echo actually gone" claim needs Aaron's machine.

Implementation choice: ``pywebrtc-audio`` (PyPI; strands-labs/pywebrtc-audio),
pre-built wheels for Linux x86_64, no build toolchain. It binds WebRTC's
AEC3 — the same echo canceller Chrome/Edge run — with a clean surface:

    from pywebrtc_audio import AudioProcessor
    ap = AudioProcessor(sample_rate=16000, num_channels=1,
                        echo_cancellation=True, noise_suppression=False,
                        auto_gain_control=False, stream_delay_ms=0)
    clean = ap.process(near, far)   # near = mic, far = speaker reference

Rejected alternatives (documented so nobody re-litigates):
  - njerig/python-webrtc-audio-processing: SWIG/meson build-from-source,
    stale (last update ~1 yr), no wheels.
  - huangjunsen0406/webrtc-audio-processing: also build-from-source.
  - speexdsp bindings: AEC is the older MDF algorithm, worse on
    double-talk than AEC3; kept as the named fallback only.
  - PipeWire libpipewire-module-echo-cancel: right answer for a
    PipeWire-native box, but it's a system module, not something the
    pipeline can instantiate per-process.

Design: :class:`AecAudioIO` is an :class:`~echo_node.slots.AudioIO`
provider that wraps :class:`~echo_node.components.audio.MicStream`'s
capture path. It keeps a far-end ring buffer — the *reference* signal
(the audio we played through the speakers) — which the playback side
feeds via :meth:`feed_far_end`. ``read()`` aligns far-end samples with
each mic chunk and runs AEC3, returning echo-cleaned audio.

Wiring gap (documented, not hidden): nothing in the pipeline currently
calls ``feed_far_end`` — InterruptibleSpeaker plays WAVs via aplay /
sounddevice and does not hand the rendered samples back. Full-duplex
wiring (speaker → feed_far_end) is Phase-C follow-up work; until then
the provider reports honestly and AEC runs on zero-padded reference
(which is just the mic signal — no worse than no AEC, and validate()
says so).
"""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any

import numpy as np

from echo_node.components.audio import AudioConfig, MicStream
from echo_node.slots import AudioIO, Capability
from echo_node.slots.validation import (
    ValidationResult,
    check_module,
    missing_result,
    ok_result,
)


class AecAudioIO(AudioIO):
    """Mic capture with WebRTC AEC3 echo cancellation.

    Constructor takes the same :class:`AudioConfig` the orchestrator
    builds (or a plain dict with the same keys — ``AudioConfig(**cfg)``).
    AEC3 needs a far-end reference: feed what the speakers are playing
    via :meth:`feed_far_end`. ``read()`` returns echo-cancelled chunks.
    """

    def __init__(self, config: AudioConfig | dict[str, Any]):
        raw: dict[str, Any] = dict(config) if isinstance(config, dict) else {}
        if isinstance(config, dict):
            config = AudioConfig(**{k: config[k] for k in
                                    ("backend", "sample_rate", "chunk_size")
                                    if k in config} |
                                 {k: v for k, v in config.items()
                                  if k in ("arecord_device", "playback_device",
                                           "input_device", "output_device")})
        self.config = config
        self._mic = MicStream(config)
        # AEC3 tuning knobs (read from the raw dict when given one).
        self._stream_delay_ms = int(raw.get("aec_stream_delay_ms", 0))
        self._ns_enabled = bool(raw.get("aec_noise_suppression", False))
        # Far-end reference: mono int16, up to 2 s of playback history.
        self._far: deque[np.ndarray] = deque()
        self._far_samples = 0
        self._far_capacity = self.config.sample_rate * 2
        self._processor: Any | None = None
        self._passthrough = False   # True when the binding is absent
        self._aec_failures = 0

    # ── Slot contract ──────────────────────────────────────────────

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(
            name="aec-webrtc",
            version="AEC3 (pywebrtc-audio)",
            languages=[],
            streaming=True,   # per-chunk read()
            gpu_required=False,
            license="BSD-3-Clause",  # WebRTC APM; pywebrtc-audio is MIT
            network=False,
            notes=("WebRTC AEC3 echo cancellation around MicStream capture; "
                   "needs feed_far_end() wired to the playback path for real "
                   "full-duplex (currently a documented gap); requires "
                   "hardware validation — echo removal cannot be proven on "
                   "a VM with no mic/speakers"),
        )

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        found, ver = check_module("pywebrtc_audio")
        if not found:
            return missing_result("pywebrtc_audio",
                                   {"module": "pywebrtc_audio (pip install pywebrtc-audio)",
                                    "fallback": "speexdsp (older MDF AEC) or "
                                                "PipeWire libpipewire-module-echo-cancel"})
        # The binding is importable, but AEC only *works* with a real
        # acoustic path: mic + speakers + a room. A VM has none of that.
        return ok_result(
            f"pywebrtc_audio {ver} importable — AEC3 available, BUT true "
            "full-duplex echo removal needs hardware validation (mic + "
            "speakers on the target machine)",
            {"version": ver, "needs_hardware_validation": True,
             "far_end_wired": False})

    # ── AudioIO contract ───────────────────────────────────────────

    def open(self) -> None:
        self._mic.open()
        self._processor = self._make_processor()

    def _make_processor(self) -> Any | None:
        try:
            from pywebrtc_audio import AudioProcessor
            return AudioProcessor(
                sample_rate=self.config.sample_rate,
                num_channels=1,
                echo_cancellation=True,
                noise_suppression=self._ns_enabled,
                high_pass_filter=False,   # auto-enabled with AEC anyway
                auto_gain_control=False,
                stream_delay_ms=self._stream_delay_ms,
            )
        except Exception:
            # Binding absent or broken at runtime: honest passthrough.
            self._passthrough = True
            return None

    def feed_far_end(self, samples: np.ndarray) -> None:
        """Hand the playback side's rendered audio back as AEC reference.

        *samples* should be mono int16 at ``config.sample_rate`` — exactly
        what was sent to the speakers. The pipeline does not call this
        yet (see module docstring); until it does, ``read()`` runs AEC
        against zero-padded reference.
        """
        chunk = np.asarray(samples, dtype=np.int16).ravel()
        self._far.append(chunk)
        self._far_samples += chunk.size
        while self._far_samples > self._far_capacity and self._far:
            dropped = self._far.popleft()
            self._far_samples -= dropped.size

    def _take_far(self, n: int) -> np.ndarray:
        """Pop up to *n* far-end samples; zero-pad when the buffer is short."""
        out = np.zeros(n, dtype=np.int16)
        filled = 0
        while filled < n and self._far:
            chunk = self._far[0]
            take = min(chunk.size, n - filled)
            out[filled:filled + take] = chunk[:take]
            filled += take
            if take < chunk.size:
                self._far[0] = chunk[take:]
                self._far_samples -= take
            else:
                self._far.popleft()
                self._far_samples -= chunk.size
        return out

    def read(self) -> np.ndarray:
        near = self._mic.read()
        if self._processor is None:
            return near  # passthrough: binding absent (see validate())
        far = self._take_far(near.size)
        try:
            # pywebrtc-audio accepts any length, int16 or float32 numpy.
            clean = self._processor.process(near, far)
            return np.asarray(clean, dtype=np.int16).ravel()[: near.size]
        except Exception:
            self._aec_failures += 1
            return near  # never break the capture path on AEC failure

    def close(self) -> None:
        try:
            if self._processor is not None and hasattr(self._processor, "reset"):
                self._processor.reset()
        finally:
            self._processor = None
            self._mic.close()

    # ── Introspection ──────────────────────────────────────────────

    @property
    def passthrough(self) -> bool:
        """True when AEC is bypassed (binding missing) — read() == mic."""
        return self._passthrough or self._processor is None

    @property
    def aec_failures(self) -> int:
        return self._aec_failures

    @property
    def far_end_buffered_s(self) -> float:
        return self._far_samples / float(self.config.sample_rate)
