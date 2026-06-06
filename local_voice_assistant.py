#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import queue
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import requests
import yaml


ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "config.yaml"


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist. Run ./setup.sh first.")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def rms_int16(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    values = samples.astype(np.float32)
    return float(math.sqrt(float(np.mean(values * values))))


@dataclass
class AudioConfig:
    sample_rate: int
    chunk_size: int
    arecord_device: str | None
    silence_rms_threshold: float
    silence_seconds: float
    max_record_seconds: float
    min_record_seconds: float


class Microphone:
    def __init__(self, config: AudioConfig):
        self.config = config
        self.process: subprocess.Popen[bytes] | None = None

    def open(self) -> None:
        if shutil.which("arecord") is None:
            raise RuntimeError("arecord is not installed.")
        command = [
            "arecord",
            "-q",
            "-f",
            "S16_LE",
            "-c",
            "1",
            "-r",
            str(self.config.sample_rate),
            "-t",
            "raw",
        ]
        if self.config.arecord_device:
            command.extend(["-D", self.config.arecord_device])
        self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def read_chunk(self) -> np.ndarray:
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
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None


class WakeWordDetector:
    def __init__(self, config: dict[str, Any]):
        self.enabled = bool(config.get("enabled", True))
        self.sensitivity = float(config.get("sensitivity", 0.35))
        self.model_paths = [str(p) for p in config.get("model_paths", [])]
        self.model = None
        if not self.enabled:
            return
        missing = [p for p in self.model_paths if not Path(p).exists()]
        if missing:
            raise FileNotFoundError(f"Wake-word model file missing: {missing[0]}")
        try:
            from openwakeword.model import Model
        except ImportError as exc:
            raise RuntimeError("openwakeword is not installed. Run ./setup.sh.") from exc
        self.model = Model(
            wakeword_models=self.model_paths,
            inference_framework="onnx",
        )

    def detected(self, samples: np.ndarray) -> tuple[bool, str, float]:
        if not self.enabled:
            return True, "disabled", 1.0
        assert self.model is not None
        prediction = self.model.predict(samples)
        if not prediction:
            return False, "", 0.0
        name, score = max(prediction.items(), key=lambda item: float(item[1]))
        score = float(score)
        return score >= self.sensitivity, name, score


class ParakeetSTT:
    def __init__(self, config: dict[str, Any]):
        self.model_name = str(config.get("model_name", "nemo-parakeet-tdt-0.6b-v2"))
        self.quantization = str(config.get("quantization", "int8"))
        self.model = None

    def load(self) -> None:
        if self.model is not None:
            return
        try:
            import onnx_asr
        except ImportError as exc:
            raise RuntimeError("onnx-asr is not installed. Run ./setup.sh.") from exc
        print(f"[stt] loading {self.model_name} ({self.quantization})", flush=True)
        self.model = onnx_asr.load_model(self.model_name, quantization=self.quantization)

    def transcribe(self, wav_path: Path) -> str:
        self.load()
        assert self.model is not None
        result = self.model.recognize(str(wav_path))
        text = result[0] if isinstance(result, list) else result
        return str(text).strip()


class EspeakTTS:
    def __init__(self, config: dict[str, Any]):
        self.voice = str(config.get("voice", "en-us"))
        self.speed = str(config.get("speed", 165))
        self.pitch = str(config.get("pitch", 45))
        if shutil.which("espeak-ng") is None:
            raise RuntimeError("espeak-ng is not installed.")
        if shutil.which("aplay") is None:
            raise RuntimeError("aplay is not installed.")

    def speak(self, text: str) -> None:
        if not text.strip():
            return
        espeak = subprocess.Popen(
            ["espeak-ng", "-v", self.voice, "-s", self.speed, "-p", self.pitch, "--stdout", text],
            stdout=subprocess.PIPE,
        )
        aplay = subprocess.Popen(["aplay", "-q"], stdin=espeak.stdout)
        if espeak.stdout is not None:
            espeak.stdout.close()
        aplay.wait()
        espeak.wait()


class AssistantBrain:
    def __init__(self, config: dict[str, Any]):
        self.base_url = str(config.get("base_url", "http://127.0.0.1:11434")).rstrip("/")
        self.model = str(config.get("model", "") or "")
        self.system_prompt = str(config.get("system_prompt", "Answer briefly."))
        self.timeout = float(config.get("timeout_seconds", 45))
        self.history: list[dict[str, str]] = []

    def available_models(self) -> list[str]:
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=3)
            response.raise_for_status()
            payload = response.json()
            return [m.get("name", "") for m in payload.get("models", []) if m.get("name")]
        except Exception:
            return []

    def choose_model(self) -> str | None:
        if self.model:
            return self.model
        models = self.available_models()
        return models[0] if models else None

    def respond(self, text: str) -> str:
        lowered = text.lower().strip()
        now = dt.datetime.now().astimezone()
        if lowered in {"time", "what time is it", "what's the time"}:
            return f"It is {now:%I:%M %p}."
        if lowered in {"date", "what date is it", "what's the date"}:
            return f"Today is {now:%A, %B %d, %Y}."
        if lowered.startswith("repeat "):
            return text[7:].strip()

        model = self.choose_model()
        if not model:
            return f"I heard: {text}. Ollama is running, but no local model is installed."

        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self.history[-8:])
        messages.append({"role": "user", "content": text})
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json={"model": model, "messages": messages, "stream": False},
                timeout=self.timeout,
            )
            response.raise_for_status()
            answer = str(response.json().get("message", {}).get("content", "")).strip()
        except Exception as exc:
            answer = f"I heard: {text}. Ollama did not answer: {exc}"

        if answer:
            self.history.append({"role": "user", "content": text})
            self.history.append({"role": "assistant", "content": answer})
        return answer


def save_wav(samples: list[np.ndarray], sample_rate: int) -> Path:
    fd, name = tempfile.mkstemp(prefix="voice-agent-", suffix=".wav")
    os.close(fd)
    path = Path(name)
    audio = np.concatenate(samples) if samples else np.array([], dtype=np.int16)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(audio.astype(np.int16).tobytes())
    return path


def record_until_silence(mic: Microphone) -> Path | None:
    cfg = mic.config
    chunks: list[np.ndarray] = []
    silence_started: float | None = None
    started = time.monotonic()
    speech_seen = False

    print("[audio] listening; stop speaking to submit", flush=True)
    while True:
        chunk = mic.read_chunk()
        chunks.append(chunk)
        level = rms_int16(chunk)
        elapsed = time.monotonic() - started

        if level >= cfg.silence_rms_threshold:
            speech_seen = True
            silence_started = None
        elif speech_seen:
            if silence_started is None:
                silence_started = time.monotonic()
            if (
                elapsed >= cfg.min_record_seconds
                and time.monotonic() - silence_started >= cfg.silence_seconds
            ):
                break

        if elapsed >= cfg.max_record_seconds:
            break

    if not speech_seen:
        print("[audio] no speech above threshold", flush=True)
        return None
    return save_wav(chunks, cfg.sample_rate)


def run(config_path: Path) -> int:
    config = load_config(config_path)
    audio_config = AudioConfig(**config["audio"])
    wake = WakeWordDetector(config.get("wake_word", {}))
    stt = ParakeetSTT(config.get("stt", {}))
    tts = EspeakTTS(config.get("tts", {}))
    brain = AssistantBrain(config.get("llm", {}))
    exit_phrases = {str(p).lower() for p in config.get("assistant", {}).get("exit_phrases", [])}

    stop = False

    def handle_signal(_signum: int, _frame: Any) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    mic = Microphone(audio_config)
    mic.open()
    print("[ready] say the wake phrase, then speak your request", flush=True)
    try:
        while not stop:
            chunk = mic.read_chunk()
            detected, name, score = wake.detected(chunk)
            if not detected:
                continue

            print(f"[wake] detected {name} ({score:.2f})", flush=True)
            tts.speak("Yes?")
            wav_path = record_until_silence(mic)
            if wav_path is None:
                tts.speak("I did not hear speech.")
                continue

            try:
                text = stt.transcribe(wav_path)
            finally:
                wav_path.unlink(missing_ok=True)

            if not text:
                print("[stt] empty transcription", flush=True)
                tts.speak("I could not transcribe that.")
                continue

            print(f"[you] {text}", flush=True)
            if text.lower().strip() in exit_phrases:
                tts.speak("Stopping.")
                break

            answer = brain.respond(text)
            print(f"[assistant] {answer}", flush=True)
            tts.speak(answer)
    finally:
        mic.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Local Parakeet STT voice assistant")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to config.yaml")
    args = parser.parse_args()
    try:
        return run(Path(args.config))
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
