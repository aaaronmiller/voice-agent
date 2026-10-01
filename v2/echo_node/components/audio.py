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
from echo_node.components.tts import CosyVoice3TTS, DotsTTS, EspeakTTS, KokoroTTS

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


# ── Mic stream ──────────────────────────────────────────────────────

class MicStream:
    def __init__(self, config: AudioConfig):
        self.config = config
        self.process: subprocess.Popen[bytes] | None = None
        self.sd_stream: Any | None = None

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
    ):
        self.audio = audio
        self.vad = vad
        self.enabled = bool(config.get("enabled", True))
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
        try:
            provider = tts_config.get("provider", "kokoro")
            if provider == "dots":
                self.tts = DotsTTS(tts_config)
            elif provider == "cosyvoice3":
                self.tts = CosyVoice3TTS(tts_config)
            elif provider == "kokoro":
                self.tts = KokoroTTS(tts_config)
            else:
                self.tts = EspeakTTS(tts_config)
        except Exception as exc:
            print(f"[tts] {tts_config.get('provider', 'kokoro')} unavailable, falling back to espeak-ng: {exc}", flush=True)
            self.tts = EspeakTTS(tts_config)

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

    def speak(self, text: str, mic: MicStream | None = None, turn_rec: Any = None) -> bool:
        interrupted = False
        first_chunk = True
        for chunk in sentence_chunks(text):
            wav = Path(tempfile.mkstemp(prefix="echo-node-say-", suffix=".wav")[1])
            try:
                if turn_rec and first_chunk:
                    turn_rec.t_tts_start = time.perf_counter()
                self.tts.synthesize_to_wav(chunk, wav)
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
                if interrupted:
                    break
            finally:
                wav.unlink(missing_ok=True)
            first_chunk = False
        if turn_rec:
            turn_rec.t_tts_done = time.perf_counter()
        return interrupted

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

    def _is_bargein_speech(self, samples: np.ndarray,
                           started: float,
                           grace_window: float,
                           original_threshold: float,
                           original_rms: float) -> bool:
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

    def _bargein_triggered(self, is_speech: bool, speech_started: float | None,
                           silence_started: float | None, now: float) -> tuple[bool, float | None, float | None]:
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

    def _play_wav(self, wav: Path, mic: MicStream | None) -> bool:
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
