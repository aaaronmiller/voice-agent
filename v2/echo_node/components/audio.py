"""Audio I/O: config, mic stream, and the interruptible TTS speaker.

Barge-in design (2026 best practice, all config-driven via ``barge_in``):
  a) VAD-gated — playback is interrupted on sustained local speech onset,
     never by waiting hundreds of ms for an STT transcript.
  b) Elevated thresholds during playback — the VAD score and RMS thresholds
     are boosted while TTS is playing so the assistant's own speaker bleed
     doesn't interrupt it (effective VAD threshold ≈ 0.86 vs 0.48 baseline).
  c) Debounce + hysteresis — ``min_speech_seconds`` (~0.22s) of sustained
     speech before triggering (kills door-slams/transients), and the pending
     trigger is only abandoned after ``bargein_end_grace_s`` of sustained
     silence so one quiet frame can't cancel a real interruption.
"""

from __future__ import annotations

import itertools
import os
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from echo_node.components._common import pop_speakable_chunk, rms_int16, sentence_chunks
from echo_node.components.barge_in import VadGatedBargeIn
from echo_node.components.tts import EspeakTTS, create_tts
from echo_node.slots import AudioIO, Capability, TTSProvider
from echo_node.slots.validation import (
    ValidationResult,
    check_binary,
    check_module,
    missing_result,
    ok_result,
)

if TYPE_CHECKING:
    from echo_node.components.vad import OpenWakeWordVad


# ── Audio config ────────────────────────────────────────────────────

@dataclass
class AudioConfig:
    backend: str
    sample_rate: int
    chunk_size: int
    arecord_device: str = "default"
    playback_device: str = "default"
    input_device: str | int | None = None
    output_device: str | int | None = None
    # Optional slot-provider override (audio.provider in config.yaml).
    # None/empty means "use backend" — the historical behaviour.
    provider: str | None = None


def create_audio_io(audio_config: dict[str, Any]) -> AudioIO:
    """Instantiate the configured audio I/O provider.

    ``audio.provider`` selects the registry provider (e.g. ``aec-webrtc``);
    when absent, the ``audio.backend`` value (``alsa``/``sounddevice``) is
    used — exactly the old hard-coded ``MicStream`` construction in the
    orchestrator. Unknown provider names fall back to ``MicStream``.
    """
    from echo_node.slots import SlotType
    from echo_node.slots.registry import get_registry
    provider = str(audio_config.get("provider")
                   or audio_config.get("backend", "alsa"))
    try:
        cls = get_registry().get(SlotType.AUDIO_IO, provider)
    except KeyError:
        print(f"[audio] unknown provider {provider!r}, falling back to MicStream",
              flush=True)
        cls = MicStream
    if cls is MicStream:
        return cls(AudioConfig(
            backend=str(audio_config.get("backend", "alsa")),
            sample_rate=int(audio_config.get("sample_rate", 16000)),
            chunk_size=int(audio_config.get("chunk_size", 1280)),
            arecord_device=str(audio_config.get("arecord_device", "default")),
            playback_device=str(audio_config.get("playback_device", "default")),
            input_device=audio_config.get("input_device"),
            output_device=audio_config.get("output_device"),
            provider=audio_config.get("provider"),
        ))
    # Slot providers other than MicStream (e.g. AecAudioIO) accept the raw
    # audio section dict.
    return cls(dict(audio_config))


# ── Mic stream ──────────────────────────────────────────────────────

class MicStream(AudioIO):
    """Mic capture; backend selected by AudioConfig.backend.

    Registered in the slot registry under both "alsa" (arecord) and
    "sounddevice", each with its own capabilities/validator.
    """
    def __init__(self, config: AudioConfig):
        self.config = config
        self.process: subprocess.Popen[bytes] | None = None
        self.sd_stream: Any | None = None

    @classmethod
    def capabilities(cls) -> Capability:
        # Generic fallback — the registry registers per-name descriptors.
        return Capability(
            name="micstream",
            streaming=True,
            license="unknown",
            network=False,
            notes="backend chosen by audio.backend: alsa (arecord) or sounddevice",
        )

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        arecord_ok, _ = check_binary("arecord")
        sd_ok, _ = check_module("sounddevice")
        if arecord_ok or sd_ok:
            return ok_result("mic capture available",
                             {"arecord": arecord_ok, "sounddevice": sd_ok})
        return missing_result("arecord and sounddevice",
                              {"arecord": False, "sounddevice": False})

    def open(self) -> None:
        if self.config.backend == "sounddevice":
            import sounddevice as sd
            self.sd_stream = sd.InputStream(
                samplerate=self.config.sample_rate,
                blocksize=self.config.chunk_size,
                channels=1,
                dtype="int16",
                device=self.config.input_device,
            )
            self.sd_stream.start()
            return
        if shutil.which("arecord") is None:
            raise RuntimeError("arecord is not installed.")
        command = [
            "arecord", "-q", "-D", self.config.arecord_device,
            "-f", "S16_LE", "-c", "1", "-r", str(self.config.sample_rate), "-t", "raw",
        ]
        self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def read(self) -> np.ndarray:
        if self.config.backend == "sounddevice":
            if self.sd_stream is None:
                raise RuntimeError("sounddevice microphone stream is not open")
            data, _overflowed = self.sd_stream.read(self.config.chunk_size)
            return np.asarray(data[:, 0], dtype=np.int16).copy()
        if self.process is None or self.process.stdout is None:
            raise RuntimeError("microphone stream is not open")
        byte_count = self.config.chunk_size * 2
        raw = self.process.stdout.read(byte_count)
        if len(raw) != byte_count:
            stderr = b""
            if self.process.stderr is not None:
                stderr = self.process.stderr.read() or b""
            raise RuntimeError(f"arecord stopped: {stderr.decode(errors='ignore').strip()}")
        return np.frombuffer(raw, dtype=np.int16)

    def close(self) -> None:
        if self.sd_stream is not None:
            self.sd_stream.stop()
            self.sd_stream.close()
            self.sd_stream = None
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None


# ── Interruptible speaker ───────────────────────────────────────────

class InterruptibleSpeaker:
    def __init__(
        self,
        audio: AudioConfig,
        vad: OpenWakeWordVad,
        config: dict[str, Any],
        tts_config: dict[str, Any],
        avatar: Any = None,
        hotkey: Any = None,
        far_end_callback: Callable[[np.ndarray], None] | None = None,
    ):
        self.audio = audio
        self.vad = vad
        self.enabled = bool(config.get("enabled", True))
        # Far-end reference for echo cancellation: called with the mono
        # int16 PCM of each played sentence (at audio.sample_rate) as
        # playback starts. None (the default) disables the tap entirely.
        self.far_end_callback = far_end_callback
        # Barge-in policy (slot provider): VAD-gated interruption with
        # playback threshold boosting, debounce and hysteresis.
        self.barge_in = VadGatedBargeIn(vad, config)
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
        # Cache the original thresholds so we can restore them
        self._orig_threshold = self.vad.threshold
        self._orig_rms_floor = self.vad.rms_floor
        self.avatar = avatar
        self.hotkey = hotkey
        # Debug data callback — called after each VAD reading during playback
        # with {"vad": 0.45, "rms": 600, "threshold": 0.40, ...}
        self.debug_callback: Callable[[dict], None] | None = None
        self.tts = create_tts(tts_config)

    def unload(self) -> None:
        self.tts.unload()

    def warm(self) -> None:
        started = time.perf_counter()
        self.tts.warm()
        print(f"[timing] tts_warm={time.perf_counter() - started:.2f}s", flush=True)

    def _send_debug(self, vad_score: float, rms_val: float, state: str) -> None:
        """Send VAD/RMS/threshold data to the avatar debug overlay and tray icon."""
        if self.debug_callback:
            self.debug_callback({
                "vad": vad_score,
                "rms": rms_val,
                "threshold": self._orig_threshold,
                "boosted_threshold": min(0.99, self._orig_threshold * self.playback_threshold_boost),
                "rms_floor": self._orig_rms_floor,
                "boosted_rms": int(self._orig_rms_floor * self.playback_rms_boost),
                "state": state,
            })

    def _tts_supports_streaming(self) -> bool:
        """True when the active TTS provider implements ``generate_stream``
        for real (overridden, not the ABC's synthesize-and-yield-one-chunk
        default). The override is the ground truth — a provider that merely
        *advertises* streaming without implementing it stays on the blocking
        path."""
        return type(self.tts).generate_stream is not TTSProvider.generate_stream

    def speak(self, text: str, mic: MicStream | None = None, turn_rec: Any = None) -> bool:
        interrupted = False
        first_chunk = True
        # Streaming playback needs no avatar: Rhubarb lip-sync requires the
        # complete utterance WAV for phoneme alignment, which is
        # fundamentally at odds with playing audio as it is generated —
        # avatar users keep the exact blocking behavior they have today.
        allow_stream = self.avatar is None and self._tts_supports_streaming()
        for sentence in sentence_chunks(text):
            if allow_stream:
                outcome, interrupted = self._speak_sentence_streaming(
                    sentence, mic, turn_rec, first_chunk)
                if outcome == "fallback":
                    # Generator failed before any audio played: safe to
                    # retry this sentence through the blocking path.
                    interrupted = self._speak_sentence_blocking(
                        sentence, mic, turn_rec, first_chunk)
                elif outcome == "disable":
                    # Generator failed mid-stream; the partial audio stands
                    # (no replay) and the rest of this speak() call uses
                    # the blocking path.
                    allow_stream = False
            else:
                interrupted = self._speak_sentence_blocking(
                    sentence, mic, turn_rec, first_chunk)
            if interrupted:
                break
            first_chunk = False
        if turn_rec:
            turn_rec.t_tts_done = time.perf_counter()
        return interrupted

    def _speak_sentence_blocking(self, sentence: str, mic: MicStream | None,
                                 turn_rec: Any, first_chunk: bool) -> bool:
        """The historical per-sentence path: synthesize the whole sentence,
        then play the WAV. Unchanged behavior, including avatar lip-sync."""
        interrupted = False
        wav = Path(tempfile.mkstemp(prefix="echo-node-say-", suffix=".wav")[1])
        try:
            if turn_rec and first_chunk:
                turn_rec.t_tts_start = time.perf_counter()
            self.tts.synthesize_to_wav(sentence, wav)
            if turn_rec and first_chunk:
                turn_rec.t_tts_first_chunk = time.perf_counter()
            if self.avatar is not None:
                # Async preload: run Rhubarb in background thread
                ready = threading.Event()
                preload_result = [False]
                def _do_preload():
                    preload_result[0] = self.avatar.preload(wav)
                    ready.set()
                t = threading.Thread(target=_do_preload, daemon=True)
                t.start()
                ready.wait(timeout=15)  # cap at 15s so speech isn't blocked forever
                if preload_result[0]:
                    self.avatar.play()
            try:
                if turn_rec and first_chunk:
                    turn_rec.t_playback_start = time.perf_counter()
                interrupted = self._play_wav(wav, mic)
                if turn_rec and first_chunk:
                    turn_rec.t_playback_done = time.perf_counter()
            finally:
                if self.avatar is not None:
                    self.avatar.stop()
        finally:
            wav.unlink(missing_ok=True)
        return interrupted

    def _speak_sentence_streaming(self, sentence: str, mic: MicStream | None,
                                  turn_rec: Any,
                                  first_chunk: bool) -> tuple[str, bool]:
        """Play one sentence from ``generate_stream()`` chunks as they arrive.

        Returns ``(outcome, interrupted)`` where outcome is ``"ok"``,
        ``"fallback"`` (generator failed before the first audio chunk —
        the caller retries this sentence via the blocking path) or
        ``"disable"`` (generator failed mid-stream; partial audio stands,
        caller uses blocking for the rest of this ``speak()`` call).
        Barge-in is polled between chunks, so an interruption never splits
        a chunk — no partial-chunk glitches.
        """
        sample_rate = getattr(self.tts, "sample_rate", None)
        if not sample_rate:
            # Can't play chunks without knowing their rate: let the
            # blocking path handle it (it reads the rate from the WAV).
            return "fallback", False
        if turn_rec and first_chunk:
            turn_rec.t_tts_start = time.perf_counter()
        try:
            gen = self.tts.generate_stream(sentence)
            first_audio = next(iter(gen))
        except Exception as exc:
            print(f"[tts] streaming failed before first chunk ({exc}); "
                  f"falling back to blocking", flush=True)
            return "fallback", False
        if turn_rec and first_chunk:
            # Honest metric: the first *audio* chunk, not the first token.
            turn_rec.t_tts_first_chunk = time.perf_counter()
        chunks = itertools.chain([first_audio], gen)
        try:
            if self.audio.backend == "sounddevice":
                interrupted = self._play_chunks_sounddevice(
                    chunks, int(sample_rate), mic, turn_rec, first_chunk)
            else:
                interrupted = self._play_chunks_aplay(
                    chunks, int(sample_rate), mic, turn_rec, first_chunk)
        except Exception as exc:
            print(f"[tts] streaming failed mid-sentence ({exc}); "
                  f"continuing in blocking mode", flush=True)
            return "disable", False
        finally:
            close = getattr(gen, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass
        return "ok", interrupted

    def speak_stream(self, chunks: Iterable[str], mic: MicStream | None = None, turn_rec: Any = None) -> tuple[bool, str]:
        interrupted = False
        buffer = ""
        full = ""
        first = True
        for piece in chunks:
            if not piece:
                continue
            print(piece, end="", flush=True)
            full += piece
            buffer += piece
            while True:
                speakable = pop_speakable_chunk(buffer)
                if speakable is None:
                    break
                text, buffer = speakable
                interrupted = self.speak(text, mic, turn_rec=turn_rec if first else None)
                first = False
                if interrupted:
                    return True, full.strip()
        if buffer.strip() and not interrupted:
            interrupted = self.speak(buffer.strip(), mic, turn_rec=turn_rec if first else None)
        return interrupted, full.strip()

    # ── Barge-in policy delegation ────────────────────────────────
    # The interruption algorithm lives in echo_node.components.barge_in
    # (VadGatedBargeIn, a BARGE_IN slot provider). These wrappers keep the
    # speaker's internal call sites unchanged.

    def _is_bargein_speech(self, samples: np.ndarray,
                           started: float,
                           grace_window: float,
                           original_threshold: float,
                           original_rms: float) -> bool:
        return self.barge_in.is_bargein_speech(
            samples, started, grace_window, original_threshold, original_rms)

    def _bargein_triggered(self, is_speech: bool, speech_started: float | None,
                           silence_started: float | None, now: float) -> tuple[bool, float | None, float | None]:
        return self.barge_in.check(is_speech, speech_started, silence_started, now)

    def _feed_far_end(self, wav: Path) -> None:
        """Hand the about-to-play WAV to the AEC far-end reference.

        Reads the file as mono int16 at the mic sample rate and calls
        ``far_end_callback``. Never raises — a broken tap must not break
        playback.
        """
        if self.far_end_callback is None:
            return
        try:
            from echo_node.components.aec import read_wav_mono16
            pcm = read_wav_mono16(wav, self.audio.sample_rate)
            self.far_end_callback(pcm)
        except Exception as exc:
            print(f"[aec] far-end tap failed ({exc}); continuing without it",
                  flush=True)

    def _play_wav(self, wav: Path, mic: MicStream | None) -> bool:
        self._feed_far_end(wav)
        if self.audio.backend == "sounddevice":
            return self._play_wav_sounddevice(wav, mic)
        if shutil.which("aplay") is None:
            raise RuntimeError("aplay is not installed.")
        command = ["aplay", "-q", "-D", self.audio.playback_device, str(wav)]
        proc = subprocess.Popen(command)
        started = time.monotonic()
        speech_started: float | None = None
        silence_started: float | None = None
        orig_t = self._orig_threshold
        orig_r = self._orig_rms_floor

        while proc.poll() is None:
            # Check hotkey interrupt (Enter key) — non-consuming flag
            if self.hotkey and self.hotkey.interrupt_requested():
                self.hotkey.triggered()
                proc.terminate()
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    proc.kill()
                print("[hotkey] playback interrupted", flush=True)
                return True
            if self.enabled and mic is not None and time.monotonic() - started >= self.min_playback_age_seconds:
                samples = mic.read()
                # Debug: send VAD/RMS data to avatar overlay
                self._send_debug(self.vad.score(samples), rms_int16(samples), "playing")
                triggered, speech_started, silence_started = self._bargein_triggered(
                    self._is_bargein_speech(samples, started, self.playback_start_grace_s, orig_t, orig_r),
                    speech_started, silence_started, time.monotonic(),
                )
                if triggered:
                    proc.terminate()
                    try:
                        proc.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    print("[barge-in] playback interrupted", flush=True)
                    return True
            else:
                time.sleep(0.03)
        return False

    def _play_wav_sounddevice(self, wav: Path, mic: MicStream | None) -> bool:
        import sounddevice as sd
        import soundfile as sf
        data, sample_rate = sf.read(str(wav), dtype="float32", always_2d=True)
        sd.play(data, sample_rate, device=self.audio.output_device, blocking=False)
        started = time.monotonic()
        speech_started: float | None = None
        silence_started: float | None = None
        orig_t = self._orig_threshold
        orig_r = self._orig_rms_floor

        try:
            while sd.get_stream().active:
                # Check hotkey interrupt (Enter key) — non-consuming flag
                if self.hotkey and self.hotkey.interrupt_requested():
                    self.hotkey.triggered()
                    sd.stop()
                    print("[hotkey] playback interrupted", flush=True)
                    return True
                if self.enabled and mic is not None and time.monotonic() - started >= self.min_playback_age_seconds:
                    samples = mic.read()
                    # Debug: send VAD/RMS data to avatar overlay
                    self._send_debug(self.vad.score(samples), rms_int16(samples), "responding")
                    triggered, speech_started, silence_started = self._bargein_triggered(
                        self._is_bargein_speech(samples, started, self.playback_start_grace_s, orig_t, orig_r),
                        speech_started, silence_started, time.monotonic(),
                    )
                    if triggered:
                        sd.stop()
                        print("[barge-in] playback interrupted", flush=True)
                        return True
                else:
                    time.sleep(0.03)
        finally:
            sd.stop()
        return False

    # ── Streaming playback (generate_stream chunks) ────────────────

    def _check_bargein_tick(self, mic: MicStream,
                            started: float, tick: list) -> bool:
        """One barge-in poll during chunked playback.

        *tick* is a ``[speech_started, silence_started]`` pair carried
        across calls. Returns True when playback must stop.
        """
        samples = mic.read()
        self._send_debug(self.vad.score(samples), rms_int16(samples), "playing")
        triggered, ss, sl = self._bargein_triggered(
            self._is_bargein_speech(samples, started, self.playback_start_grace_s,
                                    self._orig_threshold, self._orig_rms_floor),
            tick[0], tick[1], time.monotonic(),
        )
        tick[0], tick[1] = ss, sl
        return triggered

    def _tap_streamed_far_end(self, played: list[np.ndarray],
                              sample_rate: int) -> None:
        """Hand actually-played streamed PCM to the AEC far-end reference.

        Only chunks that reached the device are tapped (what was heard).
        Reuses :meth:`_feed_far_end` via a temp WAV, so resampling and the
        never-raise guarantee are shared with the blocking path. Stdlib
        ``wave`` only — no soundfile dependency.
        """
        if self.far_end_callback is None or not played:
            return
        import wave
        try:
            pcm = np.concatenate(
                [np.ascontiguousarray(c, dtype=np.float32).ravel()
                 for c in played])
            pcm16 = np.clip(pcm * 32768.0, -32768, 32767).astype(np.int16)
            fd, name = tempfile.mkstemp(prefix="echo-node-stream-", suffix=".wav")
            os.close(fd)
            try:
                with wave.open(name, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(int(sample_rate))
                    wf.writeframes(pcm16.tobytes())
                self._feed_far_end(Path(name))
            finally:
                Path(name).unlink(missing_ok=True)
        except Exception as exc:
            print(f"[aec] streamed far-end tap failed ({exc}); continuing",
                  flush=True)

    def _play_chunks_aplay(self, chunks: Iterable[np.ndarray],
                           sample_rate: int, mic: MicStream | None,
                           turn_rec: Any, first_chunk: bool) -> bool:
        """Stream float32 mono chunks to aplay's stdin as they arrive.

        Barge-in (and hotkey) are polled *between* chunks, so an
        interruption never splits a chunk. Generator exceptions propagate
        to the caller, which downgrades to the blocking path.
        """
        if shutil.which("aplay") is None:
            raise RuntimeError("aplay is not installed.")
        command = ["aplay", "-q", "-t", "raw", "-f", "FLOAT_LE", "-c", "1",
                   "-r", str(int(sample_rate)), "-D", self.audio.playback_device,
                   "-"]
        proc = subprocess.Popen(command, stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        started = time.monotonic()
        tick: list = [None, None]
        played: list[np.ndarray] = []
        try:
            first = True
            assert proc.stdin is not None
            for chunk in chunks:
                arr = np.ascontiguousarray(chunk, dtype=np.float32).ravel()
                if arr.size == 0:
                    continue
                if proc.poll() is not None:
                    raise RuntimeError("aplay exited unexpectedly mid-stream")
                if self.hotkey and self.hotkey.interrupt_requested():
                    self.hotkey.triggered()
                    print("[hotkey] playback interrupted", flush=True)
                    return True
                if (self.enabled and mic is not None
                        and time.monotonic() - started >= self.min_playback_age_seconds
                        and self._check_bargein_tick(mic, started, tick)):
                    print("[barge-in] playback interrupted", flush=True)
                    return True
                if turn_rec and first_chunk and first:
                    turn_rec.t_playback_start = time.perf_counter()
                try:
                    proc.stdin.write(arr.tobytes())
                    proc.stdin.flush()
                except BrokenPipeError as exc:
                    raise RuntimeError("aplay stdin closed unexpectedly") from exc
                played.append(arr)
                first = False
            proc.stdin.close()
            proc.wait(timeout=5)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    proc.kill()
            self._tap_streamed_far_end(played, sample_rate)
        if turn_rec and first_chunk:
            turn_rec.t_playback_done = time.perf_counter()
        return False

    def _play_chunks_sounddevice(self, chunks: Iterable[np.ndarray],
                                 sample_rate: int, mic: MicStream | None,
                                 turn_rec: Any, first_chunk: bool) -> bool:
        """Stream float32 mono chunks to a sounddevice OutputStream."""
        import sounddevice as sd
        stream = sd.OutputStream(samplerate=int(sample_rate), channels=1,
                                 dtype="float32",
                                 device=self.audio.output_device)
        started = time.monotonic()
        tick: list = [None, None]
        played: list[np.ndarray] = []
        stream.start()
        try:
            first = True
            for chunk in chunks:
                arr = np.ascontiguousarray(chunk, dtype=np.float32).ravel()
                if arr.size == 0:
                    continue
                if self.hotkey and self.hotkey.interrupt_requested():
                    self.hotkey.triggered()
                    print("[hotkey] playback interrupted", flush=True)
                    return True
                if (self.enabled and mic is not None
                        and time.monotonic() - started >= self.min_playback_age_seconds
                        and self._check_bargein_tick(mic, started, tick)):
                    print("[barge-in] playback interrupted", flush=True)
                    return True
                if turn_rec and first_chunk and first:
                    turn_rec.t_playback_start = time.perf_counter()
                stream.write(arr)
                played.append(arr)
                first = False
        finally:
            try:
                stream.stop()
            finally:
                stream.close()
            self._tap_streamed_far_end(played, sample_rate)
        if turn_rec and first_chunk:
            turn_rec.t_playback_done = time.perf_counter()
        return False
