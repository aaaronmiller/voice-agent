#!/usr/bin/env python3
"""Echo-Node v2 — local voice assistant with smart routing.

Stack: OpenWakeWord → Silero VAD → faster-whisper/dots.tts → SmartRouter → agents
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Iterable
from typing import Any

import numpy as np
import requests
import soundfile as sf
import yaml


ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "config.yaml"


# ── Env loading ─────────────────────────────────────────────────────

def _load_dotenv() -> None:
    """Load .env file if present. Values only set if not already in env."""
    candidates = [ROOT / ".env", ROOT.parent / ".env"]
    for path in candidates:
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("'\"")
            if key and val and not os.environ.get(key):
                os.environ[key] = val
        break


_load_dotenv()


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist. Run ./setup.sh first.")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


# ── Utilities ───────────────────────────────────────────────────────

def rms_int16(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    values = samples.astype(np.float32)
    return float(math.sqrt(float(np.mean(values * values))))


def sentence_chunks(text: str, max_chars: int = 240) -> list[str]:
    pieces = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p.strip()]
    chunks: list[str] = []
    current = ""
    for piece in pieces or [text.strip()]:
        if len(current) + len(piece) + 1 <= max_chars:
            current = f"{current} {piece}".strip()
        else:
            if current:
                chunks.append(current)
            current = piece
    if current:
        chunks.append(current)
    return chunks


def pop_speakable_chunk(text: str, max_chars: int = 240) -> tuple[str, str] | None:
    stripped = text.strip()
    if not stripped:
        return None
    match = re.search(r"(?<=[.!?])\s+", text)
    if match:
        return text[: match.end()].strip(), text[match.end() :]
    if len(stripped) >= max_chars:
        split_at = text.rfind(" ", 0, max_chars)
        if split_at <= 0:
            split_at = max_chars
        return text[:split_at].strip(), text[split_at:].lstrip()
    return None


def backend_error_message(exc: Exception) -> str:
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        status = exc.response.status_code
        if status == 402:
            return "The configured backend requires credits or payment for that model."
        if status == 429:
            return "The configured backend is rate limiting this model. Try again later or switch models."
        if status == 401:
            return "The configured backend rejected the API key."
        if status == 404:
            return "The configured backend could not find that model."
        return f"The configured backend returned HTTP {status}."
    return f"The configured backend did not answer: {exc}"


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


# ── Wake detector ───────────────────────────────────────────────────

class WakeDetector:
    def __init__(self, config: dict[str, Any]):
        self.enabled = bool(config.get("enabled", True))
        self.sensitivity = float(config.get("sensitivity", 0.35))
        self.model = None
        self.model_paths = [str(p) for p in config.get("model_paths", [])]
        if not self.enabled:
            return
        if not self.model_paths:
            import openwakeword
            from openwakeword.utils import download_models
            for name in config.get("pretrained", ["hey_jarvis"]):
                model_info = openwakeword.MODELS.get(str(name))
                if not model_info:
                    raise ValueError(f"Unknown OpenWakeWord pretrained model: {name}")
                download_models(model_names=[str(name)])
                self.model_paths.append(model_info["model_path"].replace(".tflite", ".onnx"))
        missing = [p for p in self.model_paths if not Path(p).exists()]
        if missing:
            raise FileNotFoundError(f"Wake-word model missing: {missing[0]}")
        from openwakeword.model import Model
        self.model = Model(wakeword_models=self.model_paths, inference_framework="onnx")

    def detect(self, samples: np.ndarray) -> tuple[bool, str, float]:
        if not self.enabled:
            return True, "disabled", 1.0
        assert self.model is not None
        scores = self.model.predict(samples)
        if not scores:
            return False, "", 0.0
        name, score = max(scores.items(), key=lambda item: float(item[1]))
        score = float(score)
        return score >= self.sensitivity, name, score


# ── Silero VAD ──────────────────────────────────────────────────────

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

class FasterWhisperSTT:
    """STT via faster-whisper (CTranslate2, CPU int8)."""
    def __init__(self, config: dict[str, Any]):
        self.model_size = str(config.get("model", "tiny"))
        self.device = str(config.get("device", "cpu"))
        self.compute_type = str(config.get("compute_type", "int8"))
        self._model = None

    def load(self) -> None:
        if self._model is not None:
            return
        from faster_whisper import WhisperModel
        started = time.perf_counter()
        print(f"[stt] loading faster-whisper {self.model_size} ({self.device}, {self.compute_type})", flush=True)
        self._model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
        print(f"[timing] stt_load={time.perf_counter() - started:.2f}s", flush=True)

    def transcribe(self, wav_path: Path) -> str:
        self.load()
        assert self._model is not None
        started = time.perf_counter()
        segments, info = self._model.transcribe(str(wav_path), language="en")
        text = " ".join(s.text.strip() for s in segments).strip()
        print(f"[timing] stt={time.perf_counter() - started:.2f}s", flush=True)
        return text


class ParakeetSTT:
    def __init__(self, config: dict[str, Any]):
        self.model_name = str(config.get("model_name", "nemo-parakeet-tdt-0.6b-v2"))
        self.quantization = str(config.get("quantization", "int8"))
        self.providers = [str(p) for p in config.get("providers", [])]
        self.model = None

    def load(self) -> None:
        if self.model is not None:
            return
        import onnx_asr
        providers = self.providers or ["CPUExecutionProvider"]
        started = time.perf_counter()
        print(f"[stt] loading {self.model_name} ({self.quantization}) providers={providers}", flush=True)
        self.model = onnx_asr.load_model(self.model_name, quantization=self.quantization, providers=providers)
        print(f"[timing] stt_load={time.perf_counter() - started:.2f}s", flush=True)

    def transcribe(self, wav_path: Path) -> str:
        self.load()
        assert self.model is not None
        started = time.perf_counter()
        result = self.model.recognize(str(wav_path))
        text = result[0] if isinstance(result, list) else result
        print(f"[timing] stt={time.perf_counter() - started:.2f}s", flush=True)
        return str(text).strip()


# ── TTS backends ────────────────────────────────────────────────────

class KokoroTTS:
    def __init__(self, config: dict[str, Any]):
        self.model_path = (ROOT / str(config.get("model_path", "models/kokoro/kokoro-v1.0.onnx"))).resolve()
        self.voices_path = (ROOT / str(config.get("voices_path", "models/kokoro/voices-v1.0.bin"))).resolve()
        self.voice = str(config.get("voice", "af_heart"))
        self.speed = float(config.get("speed", 1.0))
        self._kokoro = None

    def load(self) -> None:
        if self._kokoro is not None:
            return
        if not self.model_path.exists() or not self.voices_path.exists():
            raise FileNotFoundError("Kokoro model files missing. Run ./setup.sh.")
        from kokoro_onnx import Kokoro
        started = time.perf_counter()
        self._kokoro = Kokoro(str(self.model_path), str(self.voices_path))
        print(f"[timing] tts_load={time.perf_counter() - started:.2f}s", flush=True)

    def warm(self) -> None:
        fd, name = tempfile.mkstemp(prefix="echo-node-tts-warm-", suffix=".wav")
        os.close(fd)
        path = Path(name)
        try:
            self.synthesize_to_wav("Ready.", path)
        finally:
            path.unlink(missing_ok=True)

    def synthesize_to_wav(self, text: str, path: Path) -> Path:
        self.load()
        assert self._kokoro is not None
        audio, sample_rate = self._kokoro.create(text, voice=self.voice, speed=self.speed, lang="en-us")
        sf.write(str(path), audio, sample_rate)
        return path


class DotsTTS:
    """GPU-accelerated TTS via dots.tts (2B AR model, MeanFlow distillation)."""
    def __init__(self, config: dict[str, Any]):
        from tts_dots import DotsTTS as _DotsTTS
        self._impl = _DotsTTS(config)

    def load(self) -> None:
        self._impl.load()

    def warm(self) -> None:
        self._impl.warm()

    def synthesize_to_wav(self, text: str, path: Path) -> Path:
        started = time.perf_counter()
        result = self._impl.synthesize_to_wav(text, path)
        print(f"[timing] tts_gen={time.perf_counter() - started:.2f}s provider=dots", flush=True)
        return result

    def generate_stream(self, text: str):
        return self._impl.generate_stream(text)

    @property
    def sample_rate(self) -> int:
        return self._impl.sample_rate


class EspeakTTS:
    def __init__(self, config: dict[str, Any]):
        self.voice = str(config.get("espeak_voice", "en-us"))
        self.speed = str(config.get("espeak_speed", 165))
        self.pitch = str(config.get("espeak_pitch", 45))
        if shutil.which("espeak-ng") is None:
            raise RuntimeError("espeak-ng is not installed.")

    def synthesize_to_wav(self, text: str, path: Path) -> Path:
        subprocess.run(
            ["espeak-ng", "-v", self.voice, "-s", self.speed, "-p", self.pitch, "-w", str(path), text],
            check=True,
        )
        return path

    def warm(self) -> None:
        return


# ── Interruptible speaker ───────────────────────────────────────────

class InterruptibleSpeaker:
    def __init__(
        self,
        audio: AudioConfig,
        vad: SileroVad,
        config: dict[str, Any],
        tts_config: dict[str, Any],
        avatar: Any = None,
    ):
        self.audio = audio
        self.vad = vad
        self.enabled = bool(config.get("enabled", True))
        self.min_speech_seconds = float(config.get("min_speech_seconds", 0.22))
        self.min_playback_age_seconds = float(config.get("min_playback_age_seconds", 0.45))
        self.avatar = avatar
        try:
            provider = tts_config.get("provider", "kokoro")
            if provider == "dots":
                self.tts = DotsTTS(tts_config)
            elif provider == "kokoro":
                self.tts = KokoroTTS(tts_config)
            else:
                self.tts = EspeakTTS(tts_config)
            if provider in ("kokoro", "dots"):
                self.tts.load()
        except Exception as exc:
            print(f"[tts] {tts_config.get('provider', 'kokoro')} unavailable, falling back to espeak-ng: {exc}", flush=True)
            self.tts = EspeakTTS(tts_config)

    def warm(self) -> None:
        started = time.perf_counter()
        self.tts.warm()
        print(f"[timing] tts_warm={time.perf_counter() - started:.2f}s", flush=True)

    def speak(self, text: str, mic: MicStream | None = None) -> bool:
        interrupted = False
        for chunk in sentence_chunks(text):
            wav = Path(tempfile.mkstemp(prefix="echo-node-say-", suffix=".wav")[1])
            try:
                self.tts.synthesize_to_wav(chunk, wav)
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
                    interrupted = self._play_wav(wav, mic)
                finally:
                    if self.avatar is not None:
                        self.avatar.stop()
                if interrupted:
                    break
            finally:
                wav.unlink(missing_ok=True)
        return interrupted

    def speak_stream(self, chunks: Iterable[str], mic: MicStream | None = None) -> tuple[bool, str]:
        interrupted = False
        buffer = ""
        full = ""
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
                interrupted = self.speak(text, mic)
                if interrupted:
                    return True, full.strip()
        if buffer.strip() and not interrupted:
            interrupted = self.speak(buffer.strip(), mic)
        return interrupted, full.strip()

    def _play_wav(self, wav: Path, mic: MicStream | None) -> bool:
        if self.audio.backend == "sounddevice":
            return self._play_wav_sounddevice(wav, mic)
        if shutil.which("aplay") is None:
            raise RuntimeError("aplay is not installed.")
        command = ["aplay", "-q", "-D", self.audio.playback_device, str(wav)]
        proc = subprocess.Popen(command)
        started = time.monotonic()
        speech_started: float | None = None

        while proc.poll() is None:
            if self.enabled and mic is not None and time.monotonic() - started >= self.min_playback_age_seconds:
                samples = mic.read()
                if self.vad.is_speech(samples):
                    if speech_started is None:
                        speech_started = time.monotonic()
                    if time.monotonic() - speech_started >= self.min_speech_seconds:
                        proc.terminate()
                        try:
                            proc.wait(timeout=1)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                        print("[barge-in] playback interrupted", flush=True)
                        return True
                else:
                    speech_started = None
            else:
                time.sleep(0.03)
        return False

    def _play_wav_sounddevice(self, wav: Path, mic: MicStream | None) -> bool:
        import sounddevice as sd
        data, sample_rate = sf.read(str(wav), dtype="float32", always_2d=True)
        sd.play(data, sample_rate, device=self.audio.output_device, blocking=False)
        started = time.monotonic()
        speech_started: float | None = None

        try:
            while sd.get_stream().active:
                if self.enabled and mic is not None and time.monotonic() - started >= self.min_playback_age_seconds:
                    samples = mic.read()
                    if self.vad.is_speech(samples):
                        if speech_started is None:
                            speech_started = time.monotonic()
                        if time.monotonic() - speech_started >= self.min_speech_seconds:
                            sd.stop()
                            print("[barge-in] playback interrupted", flush=True)
                            return True
                    else:
                        speech_started = None
                else:
                    time.sleep(0.03)
        finally:
            sd.stop()
        return False


# ── LLM Router (legacy compat + direct calls) ──────────────────────

class LLMRouter:
    def __init__(self, config: dict[str, Any], system_prompt: str):
        self.provider = str(config.get("provider", "ollama"))
        self.base_url = str(config.get("base_url", "http://127.0.0.1:11434")).rstrip("/")
        self.api_key = str(config.get("api_key", "") or os.environ.get("OPENROUTER_API_KEY", ""))
        self.model = str(config.get("model", "") or "")
        self.timeout = float(config.get("timeout_seconds", 60))
        self.max_history_turns = int(config.get("max_history_turns", 8))
        self.keep_alive = str(config.get("keep_alive", "30m"))
        self.stream = bool(config.get("stream", True))
        self.system_prompt = system_prompt
        self.history: list[dict[str, str]] = []

    def warmup(self) -> None:
        if self.provider == "ollama":
            self._warmup_ollama()
        elif self.provider in {"openai-compatible", "hermes"}:
            self._warmup_openai_compatible(default_model="hermes-agent" if self.provider == "hermes" else "")
        elif self.provider == "odysseus":
            print("[warmup] skipping Odysseus backend warmup", flush=True)

    def respond(self, user_text: str) -> str:
        built_in = self._built_in(user_text)
        if built_in:
            return built_in
        if self.provider == "hermes":
            return self._openai_compatible(user_text, default_model="hermes-agent")
        if self.provider == "odysseus":
            return self._odysseus(user_text)
        if self.provider == "openai-compatible":
            return self._openai_compatible(user_text)
        return self._ollama(user_text)

    def response_chunks(self, user_text: str) -> tuple[Iterable[str], bool]:
        built_in = self._built_in(user_text)
        if built_in:
            return [built_in], False
        if not self.stream:
            return [self.respond(user_text)], False
        if self.provider == "openai-compatible":
            return self._openai_compatible_chunks(user_text), True
        if self.provider == "hermes":
            return self._openai_compatible_chunks(user_text, default_model="hermes-agent"), True
        if self.provider == "ollama":
            return self._ollama_chunks(user_text), True
        return [self.respond(user_text)], False

    def remember_response(self, user_text: str, answer: str) -> None:
        if answer:
            self._remember(user_text, answer)

    @staticmethod
    def _built_in(text: str) -> str:
        lowered = text.lower().strip()
        now = dt.datetime.now().astimezone()
        if lowered in {"time", "what time is it", "what's the time"}:
            return f"It is {now:%I:%M %p}."
        if lowered in {"date", "what date is it", "what's the date"}:
            return f"Today is {now:%A, %B %d, %Y}."
        if lowered.startswith("repeat "):
            return text[7:].strip()
        return ""

    def _messages(self, user_text: str) -> list[dict[str, str]]:
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self.history[-self.max_history_turns * 2 :])
        messages.append({"role": "user", "content": user_text})
        return messages

    def _remember(self, user_text: str, answer: str) -> None:
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": answer})

    def _ollama_model(self) -> str | None:
        if self.model:
            return self.model
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=3)
            response.raise_for_status()
            models = response.json().get("models", [])
            return models[0].get("name") if models else None
        except Exception:
            return None

    def _ollama(self, user_text: str) -> str:
        model = self._ollama_model()
        if not model:
            return f"I heard: {user_text}. No Ollama model is installed."
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json={"model": model, "messages": self._messages(user_text), "stream": False, "keep_alive": self.keep_alive},
                timeout=self.timeout,
            )
            response.raise_for_status()
            answer = str(response.json().get("message", {}).get("content", "")).strip()
        except Exception as exc:
            answer = f"I heard: {user_text}. Ollama did not answer: {exc}"
        self._remember(user_text, answer)
        return answer

    def _ollama_chunks(self, user_text: str) -> Iterable[str]:
        model = self._ollama_model()
        if not model:
            yield f"I heard: {user_text}. No Ollama model is installed."
            return
        started = time.perf_counter()
        first_token: float | None = None
        try:
            with requests.post(
                f"{self.base_url}/api/chat",
                json={"model": model, "messages": self._messages(user_text), "stream": True, "keep_alive": self.keep_alive},
                timeout=self.timeout,
                stream=True,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    data = json.loads(line.decode("utf-8"))
                    piece = str(data.get("message", {}).get("content", "") or "")
                    if piece and first_token is None:
                        first_token = time.perf_counter()
                        print(f"[timing] backend_first_token={first_token - started:.2f}s model={model}", flush=True)
                    if piece:
                        yield piece
                    if data.get("done"):
                        break
            print(f"[timing] backend_stream_total={time.perf_counter() - started:.2f}s model={model}", flush=True)
        except Exception as exc:
            yield f"I heard: {user_text}. Ollama did not answer: {exc}"

    def _warmup_ollama(self) -> None:
        model = self._ollama_model()
        if not model:
            print("[warmup] skipping Ollama backend warmup; no model installed", flush=True)
            return
        started = time.perf_counter()
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json={"model": model, "messages": [{"role": "user", "content": "Reply with OK."}], "stream": False, "keep_alive": self.keep_alive, "options": {"num_predict": 1}},
                timeout=min(self.timeout, 30),
            )
            response.raise_for_status()
            print(f"[timing] backend_warm={time.perf_counter() - started:.2f}s model={model}", flush=True)
        except Exception as exc:
            print(f"[warmup] Ollama backend warmup failed: {backend_error_message(exc)}", flush=True)

    def _openai_compatible(self, user_text: str, default_model: str = "") -> str:
        model = self.model or default_model
        if not model:
            return f"I heard: {user_text}. No OpenAI-compatible model is configured."
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            started = time.perf_counter()
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={"model": model, "messages": self._messages(user_text), "stream": False},
                timeout=self.timeout,
            )
            response.raise_for_status()
            answer = str(response.json()["choices"][0]["message"]["content"]).strip()
            print(f"[timing] backend={time.perf_counter() - started:.2f}s model={model}", flush=True)
        except Exception as exc:
            answer = f"I heard: {user_text}. {backend_error_message(exc)}"
        self._remember(user_text, answer)
        return answer

    def _openai_compatible_chunks(self, user_text: str, default_model: str = "") -> Iterable[str]:
        model = self.model or default_model
        if not model:
            yield f"I heard: {user_text}. No OpenAI-compatible model is configured."
            return
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        started = time.perf_counter()
        first_token: float | None = None
        try:
            with requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={"model": model, "messages": self._messages(user_text), "stream": True},
                timeout=self.timeout,
                stream=True,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    decoded = line.decode("utf-8")
                    if not decoded.startswith("data: "):
                        continue
                    payload = decoded[6:].strip()
                    if payload == "[DONE]":
                        break
                    data = json.loads(payload)
                    piece = str(data.get("choices", [{}])[0].get("delta", {}).get("content", "") or "")
                    if piece and first_token is None:
                        first_token = time.perf_counter()
                        print(f"[timing] backend_first_token={first_token - started:.2f}s model={model}", flush=True)
                    if piece:
                        yield piece
            print(f"[timing] backend_stream_total={time.perf_counter() - started:.2f}s model={model}", flush=True)
        except Exception as exc:
            yield f"I heard: {user_text}. {backend_error_message(exc)}"

    def _warmup_openai_compatible(self, default_model: str = "") -> None:
        model = self.model or default_model
        if not model:
            print("[warmup] skipping OpenAI-compatible backend warmup; no model configured", flush=True)
            return
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        started = time.perf_counter()
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={"model": model, "messages": [{"role": "user", "content": "Reply with OK."}], "max_tokens": 1, "stream": False},
                timeout=min(self.timeout, 30),
            )
            response.raise_for_status()
            print(f"[timing] backend_warm={time.perf_counter() - started:.2f}s model={model}", flush=True)
        except Exception as exc:
            print(f"[warmup] OpenAI-compatible backend warmup failed: {backend_error_message(exc)}", flush=True)

    def _odysseus(self, user_text: str) -> str:
        if not self.api_key:
            return "Odysseus is configured, but no API token is set."
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload: dict[str, Any] = {"message": user_text}
        if self.model:
            payload["model"] = self.model
        session_id = getattr(self, "_odysseus_session_id", "")
        if session_id:
            payload["session"] = session_id
        try:
            response = requests.post(f"{self.base_url}/api/v1/chat", headers=headers, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            self._odysseus_session_id = str(data.get("session_id", "") or session_id)
            answer = str(data.get("response", "")).strip()
            if not answer:
                answer = "Odysseus answered, but returned an empty response."
        except Exception as exc:
            answer = f"I heard: {user_text}. {backend_error_message(exc)}"
        self._remember(user_text, answer)
        return answer


# ── Keyboard hotkey listener (non-blocking, Escape key) ─────────────

class KeyboardHotkey:
    """Listens for keyboard events in a background thread.
    Supports Escape key to toggle listening, and terminal Enter.
    """

    def __init__(self, config: dict[str, Any]):
        self.enabled = bool(config.get("enabled", True))
        self.terminal_enter = bool(config.get("terminal_enter", True))
        self.escape_enabled = bool(config.get("escape_toggle", True))
        self.events: queue.Queue[str] = queue.Queue()
        self.stop = False
        self._thread: threading.Thread | None = None
        self._listener_thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.enabled:
            return
        # Terminal Enter listener (always works)
        if self.terminal_enter:
            self._thread = threading.Thread(target=self._stdin_reader, name="hotkey-enter", daemon=True)
            self._thread.start()
        # Escape key listener (Linux: /dev/input, macOS: pynput)
        if self.escape_enabled:
            self._listener_thread = threading.Thread(target=self._escape_listener, name="hotkey-escape", daemon=True)
            self._listener_thread.start()

    def triggered(self) -> bool:
        try:
            self.events.get_nowait()
            return True
        except queue.Empty:
            return False

    def close(self) -> None:
        self.stop = True

    def _stdin_reader(self) -> None:
        """Read Enter from stdin (works in any terminal)."""
        while not self.stop:
            try:
                line = sys.stdin.readline()
            except Exception:
                return
            if line == "":
                return
            self.events.put("enter")

    def _escape_listener(self) -> None:
        """Listen for Escape key press. Linux: /dev/input, fallback: no-op."""
        if sys.platform == "linux":
            self._escape_linux()
        elif sys.platform == "darwin":
            self._escape_macos()
        # On other platforms, Escape is unavailable — Enter still works

    def _escape_linux(self) -> None:
        """Read raw keyboard events from /dev/input for Escape key."""
        import glob
        # Find keyboard event device
        keyboards = glob.glob("/dev/input/event*")
        if not keyboards:
            return

        def _read_device(path: str) -> None:
            try:
                with open(path, "rb") as f:
                    while not self.stop:
                        # Read 16-byte input_event struct
                        event = f.read(16)
                        if not event or len(event) < 16:
                            break
                        # struct input_event: timeval(16 bytes) + type(2) + code(2) + value(4)
                        # type=1 (EV_KEY), code=1 (KEY_ESC), value=1 (press)
                        import struct
                        _, _, ev_type, ev_code, ev_value = struct.unpack("=llHHi", event)
                        if ev_type == 1 and ev_code == 1 and ev_value == 1:
                            self.events.put("escape")
            except (PermissionError, OSError, FileNotFoundError):
                pass

        for device in keyboards:
            threading.Thread(target=_read_device, args=(device,), daemon=True).start()

    def _escape_macos(self) -> None:
        """macOS Escape listener via pynput (optional dependency)."""
        try:
            from pynput import keyboard as _kb
            def on_press(key):
                if not self.stop and key == _kb.Key.esc:
                    self.events.put("escape")
            with _kb.Listener(on_press=on_press) as listener:
                listener.join()
        except ImportError:
            pass  # pynput not installed, Escape unavailable


# ── Native integration adapters ─────────────────────────────────────

class HermesIntegration:
    """Direct Hermes integration via its API server.

    This is a thin wrapper around LLMRouter that ensures Hermes-specific
    defaults are always correct.
    """

    def __init__(self, config: dict[str, Any]):
        self.base_url = str(config.get("base_url", "http://127.0.0.1:8642/v1")).rstrip("/")
        self.api_key = str(config.get("api_key", "") or os.environ.get("HERMES_API_KEY", ""))
        self.model = str(config.get("model", "hermes-agent"))
        self.timeout = float(config.get("timeout_seconds", 90))

    def is_available(self) -> bool:
        try:
            r = requests.get(f"{self.base_url.rstrip('/v1')}/health", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def chat(self, text: str, system: str = "") -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": text})
        try:
            r = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={"model": self.model, "messages": messages, "stream": False},
                timeout=self.timeout,
            )
            r.raise_for_status()
            return str(r.json()["choices"][0]["message"]["content"]).strip()
        except Exception as exc:
            return f"Hermes error: {exc}"


class PiIntegration:
    """Native Pi agent integration via subprocess."""

    def __init__(self, config: dict[str, Any]):
        self.command = config.get("command", ["pi", "-p"])
        self.timeout = int(config.get("timeout_seconds", 120))

    def is_available(self) -> bool:
        return shutil.which(self.command[0]) is not None

    def chat(self, text: str, system: str = "") -> str:
        cmd = self.command + [text]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)
            output = result.stdout.strip() or result.stderr.strip() or "(no output)"
            return output
        except subprocess.TimeoutExpired:
            return f"Pi agent timed out after {self.timeout}s."
        except Exception as exc:
            return f"Pi agent error: {exc}"


# ── Config validation ─────────────────────────────────────────────────

def _resolve_path(path_text: str) -> Path:
    return (ROOT / str(path_text)).resolve() if not str(path_text).startswith("/") else Path(str(path_text)).resolve()


def validate_config(config: dict[str, Any]) -> list[str]:
    """Validate config.yaml and return a list of fatal errors."""
    errors: list[str] = []

    # Required top-level sections
    for section in ["assistant", "audio", "wake_word", "vad", "barge_in", "hotkeys", "stt", "tts", "performance"]:
        if section not in config:
            errors.append(f"Missing required section: {section}")

    # Audio
    audio = config.get("audio", {})
    backend = audio.get("backend", "alsa")
    if backend not in {"alsa", "sounddevice"}:
        errors.append(f"audio.backend must be 'alsa' or 'sounddevice', got {backend!r}")
    if int(audio.get("sample_rate", 0)) <= 0:
        errors.append("audio.sample_rate must be > 0")
    if int(audio.get("chunk_size", 0)) <= 0:
        errors.append("audio.chunk_size must be > 0")

    # Wake + VAD
    wake = config.get("wake_word", {})
    if not bool(wake.get("enabled", True)) and not wake.get("model_paths"):
        # disabled is valid
        pass
    if float(wake.get("sensitivity", 0.35)) <= 0:
        errors.append("wake_word.sensitivity must be > 0")

    vad = config.get("vad", {})
    if float(vad.get("speech_threshold", 0.48)) <= 0:
        errors.append("vad.speech_threshold must be > 0")
    if float(vad.get("silence_seconds", 0.85)) <= 0:
        errors.append("vad.silence_seconds must be > 0")

    # STT
    stt = config.get("stt", {})
    provider = stt.get("provider", "parakeet")
    if provider not in {"faster-whisper", "onnx-asr", "parakeet"}:
        errors.append(f"stt.provider must be 'faster-whisper' or 'onnx-asr', got {provider!r}")

    # TTS
    tts = config.get("tts", {})
    tts_provider = tts.get("provider", "kokoro")
    if tts_provider not in {"dots", "kokoro", "espeak-ng"}:
        errors.append(f"tts.provider must be 'dots', 'kokoro', or 'espeak-ng', got {tts_provider!r}")
    if tts_provider == "dots" and tts.get("model_path") and not _resolve_path(str(tts.get("model_path"))).exists():
        errors.append(f"dots.tts model path missing: {tts.get('model_path')}")
    if tts_provider == "kokoro":
        for key in ["model_path", "voices_path"]:
            if tts.get(key) and not _resolve_path(str(tts.get(key))).exists():
                errors.append(f"Kokoro file missing: {tts.get(key)}")
    if tts_provider == "espeak-ng" and shutil.which("espeak-ng") is None:
        errors.append("tts.provider is espeak-ng but espeak-ng is not installed")
    if bool(tts.get("streaming", False)) and tts_provider != "dots":
        errors.append("tts.streaming is only supported for provider=dots")

    # Speech formatting
    speech = config.get("speech_format", {})
    if int(speech.get("max_sentences", 4)) <= 0:
        errors.append("speech_format.max_sentences must be > 0")

    # Hermes
    hermes = config.get("hermes", {})
    if hermes:
        if not str(hermes.get("base_url", "")).strip():
            errors.append("hermes.base_url is required when hermes is configured")
        if not str(hermes.get("model", "")).strip():
            errors.append("hermes.model is required when hermes is configured")

    # Pi
    pi = config.get("pi_agent", {})
    if pi:
        command = pi.get("command", [])
        if not isinstance(command, list) or not command:
            errors.append("pi_agent.command must be a non-empty list")

    return errors


# ── Main assistant ──────────────────────────────────────────────────

class Assistant:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.audio_config = AudioConfig(**config["audio"])
        self.mic = MicStream(self.audio_config)
        self.wake = WakeDetector(config.get("wake_word", {}))
        self.vad = SileroVad(config.get("vad", {}))
        self.recorder = Recorder(self.mic, self.vad, config.get("vad", {}))

        # STT
        stt_cfg = config.get("stt", {})
        stt_provider = stt_cfg.get("provider", "parakeet")
        if stt_provider == "faster-whisper":
            self.stt = FasterWhisperSTT(stt_cfg)
        else:
            self.stt = ParakeetSTT(stt_cfg)

        # Avatar
        try:
            from avatar import build as build_avatar
            self.avatar = build_avatar(config.get("avatar", {}))
        except Exception as exc:
            print(f"[avatar] disabled: import failed: {exc}", flush=True)
            self.avatar = None

        # Speaker (TTS + barge-in)
        self.speaker = InterruptibleSpeaker(
            self.audio_config, self.vad,
            config.get("barge_in", {}),
            config.get("tts", {}),
            avatar=self.avatar,
        )

        # Speech formatting
        self.speech_max_sentences = int(config.get("speech_format", {}).get("max_sentences", 4))
        self.speech_verbose = bool(config.get("speech_format", {}).get("verbose", False))

        # Hotkeys
        self.hotkey = KeyboardHotkey(config.get("hotkeys", {}))

        # Exit phrases
        assistant_cfg = config.get("assistant", {})
        self.exit_phrases = {str(p).lower() for p in assistant_cfg.get("exit_phrases", [])}
        system_prompt = str(assistant_cfg.get("system_prompt", ""))

        # Smart Router (agent_profiles)
        from echo_node.agent_profiles import get_all_agents, SmartRouter
        self._all_agents = get_all_agents()
        self.router = SmartRouter(self._all_agents, default="fast")

        # Legacy LLM (direct)
        self.llm = LLMRouter(config.get("llm", {}), system_prompt)

        # Hermes native integration
        hermes_cfg = config.get("hermes", {})
        self.hermes = HermesIntegration(hermes_cfg) if hermes_cfg else None

        # Pi native integration
        pi_cfg = config.get("pi_agent", {})
        self.pi_agent = PiIntegration(pi_cfg) if pi_cfg else None

        # Performance
        self.performance = config.get("performance", {})
        self.stop = False

        # Verbose toggle state (user can say "be verbose" to override)
        self._verbose_override = False

    def run(self) -> int:
        signal.signal(signal.SIGINT, self._stop)
        signal.signal(signal.SIGTERM, self._stop)
        self.mic.open()
        self.hotkey.start()
        self._prewarm()
        print("[ready] say the wake phrase or press Enter/Escape", flush=True)
        try:
            while not self.stop:
                # Check for hotkey triggers
                if self.hotkey.triggered():
                    event = self.hotkey.events.get_nowait() if not self.hotkey.events.empty() else ""
                    print(f"[hotkey] {event or 'manual'} trigger", flush=True)
                    self.speaker.speak("Yes?", None)
                    self._handle_turn()
                    continue

                # Normal wake word flow
                samples = self.mic.read()
                detected, name, score = self.wake.detect(samples)
                if not detected:
                    continue
                print(f"[wake] {name} {score:.2f}", flush=True)
                self.speaker.speak("Yes?", None)
                self._handle_turn()
        finally:
            self.hotkey.close()
            self.mic.close()
            if self.avatar is not None:
                self.avatar.shutdown()
        return 0

    def _handle_turn(self) -> None:
        turn_started = time.perf_counter()
        wav_path = self.recorder.record_turn()
        if wav_path is None:
            self.speaker.speak("I did not hear speech.", None)
            return
        try:
            text = self.stt.transcribe(wav_path)
        finally:
            wav_path.unlink(missing_ok=True)
        if not text:
            print("[stt] empty transcription", flush=True)
            self.speaker.speak("I could not transcribe that.", None)
            return
        print(f"[you] {text}", flush=True)

        # Check exit phrases
        if text.lower().strip() in self.exit_phrases:
            self.speaker.speak("Stopping.", None)
            self.stop = True
            return

        # Check verbose toggle commands
        lower = text.lower().strip()
        if lower in {"be verbose", "verbose mode", "verbose on"}:
            self._verbose_override = True
            self.speaker.speak("Verbose mode on. I will give longer replies.", None)
            return
        if lower in {"be concise", "concise mode", "verbose off", "normal mode"}:
            self._verbose_override = False
            self.speaker.speak("Concise mode on. Short replies.", None)
            return

        # Check for direct Hermes command: "ask hermes ..."
        if lower.startswith("ask hermes ") or lower.startswith("hermes, "):
            query = text[len("ask hermes "):] if lower.startswith("ask hermes ") else text[len("hermes, "):]
            self._handle_hermes_direct(query)
            return

        # Check for direct Pi command: "ask pi ..."
        if lower.startswith("ask pi ") or lower.startswith("pi, "):
            query = text[len("ask pi "):] if lower.startswith("ask pi ") else text[len("pi, "):]
            self._handle_pi_direct(query)
            return

        # Smart route through agent_profiles
        route_key = self.router.classify(text)
        print(f"[router] {route_key} → {self.router.agents[route_key].name}", flush=True)

        # If Hermes is available and route is hermes, use native integration
        if route_key == "hermes" and self.hermes and self.hermes.is_available():
            answer = self.hermes.chat(text, str(self.config.get("assistant", {}).get("system_prompt", "")))
        else:
            system = self.config.get("assistant", {}).get("system_prompt", "")
            result = self.router.route(text, system)
            answer = result.text

        # Format for speech
        answer = self._format_reply(answer)

        print(f"[assistant/{route_key}] {answer}", flush=True)
        interrupted = self.speaker.speak(answer, self.mic)
        print(f"[timing] turn_total={time.perf_counter() - turn_started:.2f}s route={route_key}", flush=True)
        if interrupted:
            self._handle_turn()

    def _handle_hermes_direct(self, query: str) -> None:
        """Direct Hermes invocation with guaranteed tool access."""
        if not self.hermes or not self.hermes.is_available():
            self.speaker.speak("Hermes is not running. Start the Hermes gateway first.", None)
            return
        print(f"[hermes] {query}", flush=True)
        answer = self.hermes.chat(query, str(self.config.get("assistant", {}).get("system_prompt", "")))
        answer = self._format_reply(answer)
        print(f"[hermes] {answer}", flush=True)
        interrupted = self.speaker.speak(answer, self.mic)
        if interrupted:
            self._handle_turn()

    def _handle_pi_direct(self, query: str) -> None:
        """Direct Pi agent invocation."""
        if not self.pi_agent or not self.pi_agent.is_available():
            self.speaker.speak("Pi agent is not available.", None)
            return
        print(f"[pi] {query}", flush=True)
        answer = self.pi_agent.chat(query)
        answer = self._format_reply(answer)
        print(f"[pi] {answer}", flush=True)
        interrupted = self.speaker.speak(answer, self.mic)
        if interrupted:
            self._handle_turn()

    def _format_reply(self, text: str) -> str:
        """Apply speech formatting to a reply."""
        from echo_node.speech_format import format_for_speech
        verbose = self._verbose_override or self.speech_verbose
        return format_for_speech(
            text,
            max_sentences=self.speech_max_sentences,
            verbose=verbose,
        )

    def _prewarm(self) -> None:
        started = time.perf_counter()
        if bool(self.performance.get("preload_stt", True)):
            try:
                self.stt.load()
            except Exception as exc:
                print(f"[warmup] STT preload failed: {exc}", flush=True)
        if bool(self.performance.get("warm_tts", True)):
            try:
                self.speaker.warm()
            except Exception as exc:
                print(f"[warmup] TTS warmup failed: {exc}", flush=True)
        if bool(self.performance.get("warm_backend", False)):
            self.llm.warmup()
        print(f"[timing] prewarm_total={time.perf_counter() - started:.2f}s", flush=True)

    def _stop(self, _signum: int, _frame: Any) -> None:
        self.stop = True


def main() -> int:
    parser = argparse.ArgumentParser(description="Echo-Node v2 local voice assistant")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args()
    try:
        return Assistant(load_config(Path(args.config))).run()
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
