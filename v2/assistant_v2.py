#!/usr/bin/env python3
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


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist. Run ./setup.sh first.")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


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


@dataclass
class AudioConfig:
    backend: str
    sample_rate: int
    chunk_size: int
    arecord_device: str = "default"
    playback_device: str = "default"
    input_device: str | int | None = None
    output_device: str | int | None = None


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
            "arecord",
            "-q",
            "-D",
            self.config.arecord_device,
            "-f",
            "S16_LE",
            "-c",
            "1",
            "-r",
            str(self.config.sample_rate),
            "-t",
            "raw",
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

        providers = self.providers
        if not providers:
            providers = ["CPUExecutionProvider"]

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
            self.tts = KokoroTTS(tts_config) if tts_config.get("provider", "kokoro") == "kokoro" else EspeakTTS(tts_config)
            if isinstance(self.tts, KokoroTTS):
                self.tts.load()
        except Exception as exc:
            print(f"[tts] Kokoro unavailable, falling back to espeak-ng: {exc}", flush=True)
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
                    self.avatar.preload(wav)
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


class LLMRouter:
    def __init__(self, config: dict[str, Any], system_prompt: str):
        self.provider = str(config.get("provider", "ollama"))
        self.base_url = str(config.get("base_url", "http://127.0.0.1:11434")).rstrip("/")
        self.api_key = str(config.get("api_key", ""))
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
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Reply with OK."}],
                    "stream": False,
                    "keep_alive": self.keep_alive,
                    "options": {"num_predict": 1},
                },
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
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Reply with OK."}],
                    "max_tokens": 1,
                    "stream": False,
                },
                timeout=min(self.timeout, 30),
            )
            response.raise_for_status()
            print(f"[timing] backend_warm={time.perf_counter() - started:.2f}s model={model}", flush=True)
        except Exception as exc:
            print(f"[warmup] OpenAI-compatible backend warmup failed: {backend_error_message(exc)}", flush=True)

    def _odysseus(self, user_text: str) -> str:
        if not self.api_key:
            return "Odysseus is configured, but no API token is set. Create a chat-scoped Odysseus API token and put it in llm.api_key."
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {"message": user_text}
        if self.model:
            payload["model"] = self.model
        session_id = getattr(self, "_odysseus_session_id", "")
        if session_id:
            payload["session"] = session_id
        try:
            response = requests.post(
                f"{self.base_url}/api/v1/chat",
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
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


class TerminalHotkey:
    def __init__(self, config: dict[str, Any]):
        self.enabled = bool(config.get("enabled", False)) and bool(config.get("terminal_enter", True))
        self.events: queue.Queue[str] = queue.Queue()
        self.stop = False
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.enabled:
            return
        self.thread = threading.Thread(target=self._reader, name="terminal-hotkey", daemon=True)
        self.thread.start()

    def triggered(self) -> bool:
        try:
            self.events.get_nowait()
            return True
        except queue.Empty:
            return False

    def close(self) -> None:
        self.stop = True

    def _reader(self) -> None:
        while not self.stop:
            try:
                line = sys.stdin.readline()
            except Exception:
                return
            if line == "":
                return
            self.events.put("enter")


class Assistant:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.audio_config = AudioConfig(**config["audio"])
        self.mic = MicStream(self.audio_config)
        self.wake = WakeDetector(config.get("wake_word", {}))
        self.vad = SileroVad(config.get("vad", {}))
        self.recorder = Recorder(self.mic, self.vad, config.get("vad", {}))
        self.stt = ParakeetSTT(config.get("stt", {}))
        try:
            from avatar import build as build_avatar  # local import keeps PyQt6 optional
            self.avatar = build_avatar(config.get("avatar", {}))
        except Exception as exc:
            print(f"[avatar] disabled: import failed: {exc}", flush=True)
            self.avatar = None
        self.speaker = InterruptibleSpeaker(
            self.audio_config,
            self.vad,
            config.get("barge_in", {}),
            config.get("tts", {}),
            avatar=self.avatar,
        )
        assistant_cfg = config.get("assistant", {})
        self.exit_phrases = {str(p).lower() for p in assistant_cfg.get("exit_phrases", [])}
        self.llm = LLMRouter(config.get("llm", {}), str(assistant_cfg.get("system_prompt", "")))
        self.hotkey = TerminalHotkey(config.get("hotkeys", {}))
        self.performance = config.get("performance", {})
        self.stop = False

    def run(self) -> int:
        signal.signal(signal.SIGINT, self._stop)
        signal.signal(signal.SIGTERM, self._stop)
        self.mic.open()
        self.hotkey.start()
        self._prewarm()
        print("[ready] say the wake phrase or press Enter", flush=True)
        try:
            while not self.stop:
                samples = self.mic.read()
                if self.hotkey.triggered():
                    print("[hotkey] manual trigger", flush=True)
                    self.speaker.speak("Yes?", None)
                    self._handle_turn()
                    continue
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
        if text.lower().strip() in self.exit_phrases:
            self.speaker.speak("Stopping.", None)
            self.stop = True
            return
        chunks, should_remember = self.llm.response_chunks(text)
        print("[assistant] ", end="", flush=True)
        interrupted, answer = self.speaker.speak_stream(chunks, self.mic)
        print(flush=True)
        if should_remember:
            self.llm.remember_response(text, answer)
        print(f"[timing] turn_total={time.perf_counter() - turn_started:.2f}s", flush=True)
        if interrupted:
            self._handle_turn()

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
