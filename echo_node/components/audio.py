"""
Echo-Node Audio Components — mic capture, speaker playback, barge-in.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
import soundfile as sf


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


# ── Wake detector ───────────────────────────────────────────────────


# ── Interruptible speaker ───────────────────────────────────────────

class InterruptibleSpeaker:
    def __init__(
        self,
        audio: AudioConfig,
        vad: "SileroVad",
        config: dict[str, Any],
        tts_config: dict[str, Any],
        avatar: Any = None,
        hotkey: Any = None,
    ):
        self.audio = audio
        self.vad = vad
        self.enabled = bool(config.get("enabled", True))
        self.min_speech_seconds = float(config.get("min_speech_seconds", 0.22))
        self.min_playback_age_seconds = float(config.get("min_playback_age_seconds", 0.45))
        self.playback_threshold_boost = float(config.get("playback_threshold_boost", 1.8))
        self.playback_rms_boost = float(config.get("playback_rms_boost", 2.0))
        self.playback_start_grace_s = float(config.get("playback_start_grace_s", 0.3))
        self._orig_threshold = vad.threshold
        self._orig_rms_floor = vad.rms_floor
        self.avatar = avatar
        self.hotkey = hotkey
        self.debug_callback: Callable[[dict], None] | None = None
        try:
            provider = tts_config.get("provider", "kokoro")
            if provider == "dots":
                from echo_node.components.tts import DotsTTS
                self.tts = DotsTTS(tts_config)
            elif provider == "kokoro":
                from echo_node.components.tts import KokoroTTS
                self.tts = KokoroTTS(tts_config)
            else:
                from echo_node.components.tts import EspeakTTS
                self.tts = EspeakTTS(tts_config)
        except Exception as exc:
            print(f"[tts] {tts_config.get('provider', 'kokoro')} unavailable, falling back to espeak-ng: {exc}", flush=True)
            from echo_node.components.tts import EspeakTTS
            self.tts = EspeakTTS(tts_config)

    def unload(self) -> None:
        self.tts.unload()

    def warm(self) -> None:
        started = time.perf_counter()
        self.tts.warm()
        print(f"[timing] tts_warm={time.perf_counter() - started:.2f}s", flush=True)
        self._orig_threshold = self.vad.threshold
        self._orig_rms_floor = self.vad.rms_floor

    def speak(
        self,
        text: str,
        mic_stream: Any = None,
        turn_rec: Any = None,
    ) -> bool:
        """
        Speak text through TTS with interruptible playback.
        Returns True if interrupted (barge-in detected), False if completed.
        """
        if not self.enabled:
            print(text, flush=True)
            return False

        fd, wav_path = tempfile.mkstemp(prefix="echo-node-speak-", suffix=".wav")
        os.close(fd)
        path = Path(wav_path)

        try:
            self.tts.synthesize_to_wav(text, path)
            return self._playback(path, mic_stream, turn_rec)
        finally:
            path.unlink(missing_ok=True)

    def speak_stream(
        self,
        token_stream: Iterable[str],
        mic_stream: Any = None,
        turn_rec: Any = None,
    ) -> tuple[bool, str]:
        """
        Speak streaming text. Yields audio as it becomes available.
        Returns (interrupted, full_text).
        """
        if not self.enabled:
            full = "".join(token_stream)
            print(full, flush=True)
            return False, full

        collected: list[str] = []
        chunks: list[Path] = []
        interrupted = False

        for token in token_stream:
            if token:
                collected.append(token)
                sentence = token.strip()
                if sentence.endswith(('.', '!', '?', ':', ';')):
                    fd, tmp = tempfile.mkstemp(prefix="echo-node-stream-", suffix=".wav")
                    os.close(fd)
                    path = Path(tmp)
                    try:
                        self.tts.synthesize_to_wav("".join(collected), path)
                        chunks.append(path)
                        collected.clear()
                        if self._playback(path, mic_stream, turn_rec, is_streaming=True):
                            interrupted = True
                            break
                    except Exception:
                        path.unlink(missing_ok=True)

        # Flush remaining
        if collected and not interrupted:
            fd, tmp = tempfile.mkstemp(prefix="echo-node-stream-", suffix=".wav")
            os.close(fd)
            path = Path(tmp)
            try:
                self.tts.synthesize_to_wav("".join(collected), path)
                chunks.append(path)
                self._playback(path, mic_stream, turn_rec, is_streaming=True)
            finally:
                path.unlink(missing_ok=True)

        # Cleanup all temp files
        for p in chunks:
            p.unlink(missing_ok=True)

        full_text = "".join(chunks)  # placeholder — caller should accumulate
        return interrupted, ""

    def _playback(
        self,
        wav_path: Path,
        mic_stream: Any = None,
        turn_rec: Any = None,
        is_streaming: bool = False,
    ) -> bool:
        """
        Play a WAV file through the speaker with barge-in detection.
        Returns True if interrupted, False if completed.
        """
        import sounddevice as sd

        data, sr = sf.read(str(wav_path))
        if data.ndim == 1:
            data = data.reshape(-1, 1)
        if sr != 24000:
            import samplerate
            ratio = 24000 / sr
            data = samplerate.resample(data, ratio, "sinc_best").astype(np.float32)
            sr = 24000

        write_size = int(sr * 0.05)  # 50ms chunks for VAD checking
        interrupted = False
        started = time.perf_counter()
        playback_started = False

        if turn_rec is not None:
            turn_rec.t_playback_start = started

        # Boost VAD thresholds during playback to avoid self-triggering
        self.vad.threshold = self._orig_threshold * self.playback_threshold_boost
        self.vad.rms_floor = self._orig_rms_floor * self.playback_rms_boost

        sd.default.device = self.audio.output_device
        sd.default.samplerate = sr
        out = sd.OutputStream(samplerate=sr, channels=1, dtype=np.float32)
        out.start()

        try:
            for pos in range(0, len(data), write_size):
                chunk = data[pos:pos + write_size]
                out.write(chunk)

                now = time.perf_counter()
                elapsed = now - started

                if not playback_started:
                    playback_started = True
                    if turn_rec is not None:
                        turn_rec.t_playback_start = now

                if elapsed < self.playback_start_grace_s:
                    continue

                if mic_stream is not None and elapsed >= self.min_playback_age_seconds:
                    mic_data = mic_stream.read()
                    speech_score = self.vad.score(mic_data)
                    rms = rms_int16(mic_data)

                    debug_info = {
                        "vad": speech_score,
                        "rms": int(rms),
                        "threshold": self.vad.threshold,
                        "rms_floor": self.vad.rms_floor,
                        "elapsed": f"{elapsed:.2f}s",
                    }
                    if self.debug_callback:
                        self.debug_callback(debug_info)

                    if speech_score >= self.vad.threshold or rms >= self.vad.rms_floor:
                        if elapsed >= self.min_playback_age_seconds:
                            interrupted = True
                            if turn_rec is not None:
                                turn_rec.interrupted = True
                            break
        finally:
            out.stop()
            out.close()
            # Restore original thresholds
            self.vad.threshold = self._orig_threshold
            self.vad.rms_floor = self._orig_rms_floor

        if turn_rec is not None:
            turn_rec.t_playback_done = time.perf_counter()
            if not is_streaming or pos + write_size >= len(data):
                turn_rec.t_playback_done = time.perf_counter()

        return interrupted
