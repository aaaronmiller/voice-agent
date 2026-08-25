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
from collections.abc import Callable, Iterable
from typing import Any

import numpy as np
import requests
import soundfile as sf
import yaml

from echo_node.backends import AgentBackend, create_backend, REGISTRY, BACKEND_LABELS
from echo_node.conversation_logger import ConversationLogger, TurnRecord


ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "config.yaml"

# ── Import from modular components (Phase 4) ──
from echo_node.components.audio import AudioConfig, MicStream, InterruptibleSpeaker
from echo_node.components.vad import SileroVad, Recorder
from echo_node.components.wake import WakeDetector
from echo_node.components.stt import FasterWhisperSTT, ParakeetSTT
from echo_node.components.tts import KokoroTTS, DotsTTS, EspeakTTS
from echo_node.pipeline.router import LLMRouter
from echo_node.pipeline.hotkey import KeyboardHotkey
from echo_node.pipeline.integrations import HermesIntegration, PiIntegration
from echo_node.pipeline.orchestrator import Assistant


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


def _apply_env_overrides(config: dict[str, Any]) -> None:
    """Let env vars override config for provider/model selection, so the LLM,
    STT and TTS backends are all adjustable without editing config.yaml.

    Env always wins over the file; empty/unset vars are ignored. This only
    remaps values into the existing config sections — the provider dispatch
    (LLMRouter / STT factory / TTS factory) is unchanged.
    """
    # env var -> list of (section, key) targets it writes to
    mapping: dict[str, list[tuple[str, str]]] = {
        # LLM
        "ECHO_LLM_PROVIDER": [("llm", "provider")],
        "ECHO_LLM_MODEL": [("llm", "model")],
        "ECHO_LLM_BASE_URL": [("llm", "base_url")],
        "ECHO_LLM_API_KEY": [("llm", "api_key")],
        # STT (model_name is parakeet/onnx-asr, model is faster-whisper)
        "ECHO_STT_PROVIDER": [("stt", "provider")],
        "ECHO_STT_MODEL": [("stt", "model_name"), ("stt", "model")],
        # TTS (voice is kokoro/dots, espeak_voice is espeak-ng)
        "ECHO_TTS_PROVIDER": [("tts", "provider")],
        "ECHO_TTS_VOICE": [("tts", "voice"), ("tts", "espeak_voice")],
        # Wake word
        "ECHO_WAKE_PHRASE": [("assistant", "wake_phrase")],
    }
    applied: list[str] = []
    for env_key, targets in mapping.items():
        val = os.environ.get(env_key)
        if not val:
            continue
        for section, key in targets:
            sec = config.setdefault(section, {})
            if isinstance(sec, dict):
                sec[key] = val
        applied.append(f"{env_key}->{'***' if 'API_KEY' in env_key else val}")
    if applied:
        print(f"[config] env overrides applied: {', '.join(applied)}", flush=True)


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist. Run ./setup.sh first.")
    config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    _apply_env_overrides(config)
    return config


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

def _play_gotit_wav() -> None:
    """Play the 'got it' chime asynchronously via aplay.
    If the WAV doesn't exist or aplay fails, silently ignore."""
    if not _GOTIT_WAV.exists():
        return
    try:
        subprocess.Popen(
            ["aplay", "-q", str(_GOTIT_WAV)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        pass  # aplay not available


def main() -> int:
    parser = argparse.ArgumentParser(description="BabelFish voice assistant")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args()
    try:
        return Assistant(load_config(Path(args.config))).run()
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
