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

Wiring: the orchestrator (``echo_node/pipeline/orchestrator.py``) selects
the audio_io provider via ``create_audio_io`` (``audio.provider`` in
config.yaml, defaulting to the ``audio.backend`` behaviour) and, when the
active provider exposes ``feed_far_end``, passes it to
``InterruptibleSpeaker`` as ``far_end_callback``. The speaker feeds each
sentence WAV's PCM (resampled to the mic rate) at playback start, so the
reference buffer tracks what the speakers are actually emitting. Alignment
is approximate — AEC3 absorbs modest delay via ``aec_stream_delay_ms`` —
but it is a real far-end signal, not zero-padding.
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


def read_wav_mono16(path: str | Path, target_sr: int) -> np.ndarray:
    """Read a WAV file as mono int16 at *target_sr* (linear resample).

    Uses ``soundfile`` when importable (handles float WAVs), otherwise the
    stdlib ``wave`` module (PCM only). Multi-channel input is averaged to
    mono. Raises a clear error when the format can't be read.
    """
    data: np.ndarray
    src_sr: int
    try:
        import soundfile as sf
        raw, src_sr = sf.read(str(path), dtype="float32", always_2d=True)
        data = np.asarray(raw, dtype=np.float32)
        data = data.mean(axis=1)  # stereo → mono
    except ImportError:
        import wave
        try:
            with wave.open(str(path), "rb") as wf:
                nchan = wf.getnchannels()
                src_sr = wf.getframerate()
                sampwidth = wf.getsampwidth()
                nframes = wf.getnframes()
                frames = wf.readframes(nframes)
        except (wave.Error, EOFError, OSError) as exc:
            raise ValueError(f"cannot read wav {path}: {exc}") from exc
        if sampwidth == 1:
            # 8-bit PCM is unsigned with 128 bias.
            data = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32)
                    - 128.0) / 128.0
        elif sampwidth == 2:
            data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        else:
            raise ValueError(
                f"cannot read wav {path}: {sampwidth * 8}-bit PCM needs "
                "soundfile (pip install soundfile)")
        if nchan > 1:
            data = data.reshape(-1, nchan).mean(axis=1)
    if src_sr != target_sr and data.size:
        # Linear resample — good enough for an echo reference signal.
        src_t = np.linspace(0.0, 1.0, data.size, endpoint=False)
        dst_n = int(round(data.size * target_sr / src_sr))
        dst_t = np.linspace(0.0, 1.0, dst_n, endpoint=False)
        data = np.interp(dst_t, src_t, data).astype(np.float32)
    pcm = np.clip(data * 32768.0, -32768, 32767).astype(np.int16)
    return pcm.ravel()


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
                   "the orchestrator feeds each played sentence to "
                   "feed_far_end() when this provider is active; requires "
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
             "far_end_wiring": "orchestrator passes feed_far_end to the "
                               "speaker when aec-webrtc is the active "
                               "audio_io provider"})

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
        what was sent to the speakers. The orchestrator wires this to the
        speaker's ``far_end_callback`` when this provider is active, so
        each played sentence lands in the reference buffer at playback
        start; until the first playback, ``read()`` runs AEC against
        zero-padded reference.
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
