#!/usr/bin/env python3
"""Echo-Node v2 — local voice assistant with smart routing.

Stack: OpenWakeWord (wake-word + VAD) → Parakeet/faster-whisper → SmartRouter → agents
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

from echo_node.backends import AgentBackend, create_backend, REGISTRY, BACKEND_LABELS
from echo_node.conversation_logger import ConversationLogger, TurnRecord


ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "config.yaml"

# ── Import from modular components (Phase 4) ──
# (rms/sentence helpers live here as re-exports for scripts that did
#  `from assistant_v2 import ...`; the single source of truth is _common.)
from echo_node.components._common import rms_int16, sentence_chunks, pop_speakable_chunk, backend_error_message
from echo_node.components.audio import AudioConfig, MicStream, InterruptibleSpeaker
from echo_node.components.vad import OpenWakeWordVad, SileroVad, Recorder
from echo_node.components.wake import WakeDetector
from echo_node.components.stt import FasterWhisperSTT, ParakeetSTT
from echo_node.components.tts import KokoroTTS, DotsTTS, EspeakTTS
from echo_node.pipeline.router import LLMRouter
from echo_node.pipeline.hotkey import KeyboardHotkey
from echo_node.pipeline.integrations import HermesIntegration, PiIntegration
from echo_node.pipeline.orchestrator import Assistant

# Public re-export surface: external scripts (test.sh et al.) import these
# names from assistant_v2. Single source of truth lives in echo_node/*.
__all__ = [
    "AudioConfig", "MicStream", "InterruptibleSpeaker",
    "OpenWakeWordVad", "SileroVad", "Recorder",
    "WakeDetector",
    "FasterWhisperSTT", "ParakeetSTT",
    "KokoroTTS", "DotsTTS", "EspeakTTS",
    "LLMRouter", "KeyboardHotkey",
    "HermesIntegration", "PiIntegration",
    "Assistant",
    "rms_int16", "sentence_chunks", "pop_speakable_chunk", "backend_error_message",
    "AgentBackend", "create_backend", "REGISTRY", "BACKEND_LABELS",
    "ConversationLogger", "TurnRecord",
    "load_config", "validate_config", "main",
]


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
# rms/sentence/chunk helpers and backend_error_message now live in
# echo_node.components._common (re-exported at this module's top).


# ── Paths & validation ────────────────────────────────────────────

def _resolve_path(path_text: str) -> Path:
    return (ROOT / str(path_text)).resolve() if not str(path_text).startswith("/") else Path(str(path_text)).resolve()


def validate_config(config: dict[str, Any]) -> list[str]:
    """Validate config.yaml and return a list of fatal errors."""
    from echo_node.slots import SlotType
    from echo_node.slots.registry import get_registry
    reg = get_registry()
    errors: list[str] = []

    # Required top-level sections
    for section in ["assistant", "audio", "wake_word", "vad", "barge_in", "hotkeys", "stt", "tts", "performance"]:
        if section not in config:
            errors.append(f"Missing required section: {section}")

    # Audio (backend names come from the AUDIO_IO slot registry)
    audio = config.get("audio", {})
    backend = audio.get("backend", "alsa")
    audio_names = set(reg.all_names(SlotType.AUDIO_IO))
    if backend not in audio_names:
        errors.append(f"audio.backend must be one of {sorted(audio_names)}, got {backend!r}")
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

    # STT (provider names come from the STT slot registry)
    stt = config.get("stt", {})
    provider = stt.get("provider", "parakeet")
    stt_names = set(reg.all_names(SlotType.STT))
    if provider not in stt_names:
        errors.append(f"stt.provider must be one of {sorted(stt_names)}, got {provider!r}")

    # TTS (provider names come from the TTS slot registry)
    tts = config.get("tts", {})
    tts_provider = tts.get("provider", "kokoro")
    tts_names = set(reg.all_names(SlotType.TTS))
    if tts_provider not in tts_names:
        errors.append(f"tts.provider must be one of {sorted(tts_names)}, got {tts_provider!r}")
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
# (_play_gotit_wav lives in echo_node.pipeline.orchestrator, next to Assistant)


def main() -> int:
    parser = argparse.ArgumentParser(description="Echo-Node v2 voice assistant")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args()
    try:
        config = load_config(Path(args.config))
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    # Phase B: external (subprocess) providers are declared in the config
    # file — the trust boundary. They join the slot registry before
    # validation so `stt.provider: <external-name>` etc. resolve.
    try:
        from echo_node.adapters import (
            ExternalProviderError,
            register_external_providers,
        )
        ext_names = register_external_providers(config)
    except ExternalProviderError as exc:
        print(f"[error] external_providers: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"[error] external provider registration failed: {exc}", file=sys.stderr)
        return 1
    if ext_names:
        print(f"[config] external providers registered: {', '.join(ext_names)}", flush=True)
    try:
        errors = validate_config(config)
    except Exception as exc:
        print(f"[error] config validation failed: {exc}", file=sys.stderr)
        return 1
    if errors:
        for err in errors:
            print(f"[config] {err}", file=sys.stderr)
        return 1
    try:
        return Assistant(config).run()
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
