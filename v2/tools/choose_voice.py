#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import soundfile as sf
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.yaml"


def load_config() -> dict[str, Any]:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}


def save_config(config: dict[str, Any]) -> None:
    CONFIG_PATH.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def kokoro(config: dict[str, Any]):
    from kokoro_onnx import Kokoro

    tts = config.get("tts", {})
    return Kokoro(str(ROOT / tts["model_path"]), str(ROOT / tts["voices_path"]))


def synthesize(config: dict[str, Any], voice: str, text: str) -> Path:
    k = kokoro(config)
    speed = float(config.get("tts", {}).get("speed", 1.0))
    audio, sample_rate = k.create(text, voice=voice, speed=speed, lang="en-us")
    path = Path(tempfile.mkstemp(prefix=f"echo-node-{voice}-", suffix=".wav")[1])
    sf.write(str(path), audio, sample_rate)
    return path


def play(config: dict[str, Any], wav: Path) -> None:
    audio = config.get("audio", {})
    backend = audio.get("backend", "alsa")
    if backend == "sounddevice":
        import sounddevice as sd

        data, sample_rate = sf.read(str(wav), dtype="float32", always_2d=True)
        sd.play(data, sample_rate, device=audio.get("output_device"), blocking=True)
    else:
        subprocess.run(["aplay", "-q", "-D", audio.get("playback_device", "default"), str(wav)], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="List, audition, and configure Kokoro voices.")
    parser.add_argument("--list", action="store_true", help="List installed Kokoro voice names.")
    parser.add_argument("--voices", nargs="*", help="Voice names to audition.")
    parser.add_argument("--text", default="Hello. This is Echo Node speaking with a local Kokoro voice.")
    parser.add_argument("--set", dest="set_voice", help="Set config.yaml tts.voice to this voice.")
    args = parser.parse_args()

    config = load_config()
    voices = kokoro(config).get_voices()

    if args.list:
        for voice in voices:
            print(voice)
        return 0

    if args.set_voice:
        if args.set_voice not in voices:
            raise SystemExit(f"Unknown voice: {args.set_voice}")
        config.setdefault("tts", {})["voice"] = args.set_voice
        save_config(config)
        print(f"Configured tts.voice: {args.set_voice}")
        return 0

    selected = args.voices or ["af_heart", "af_bella", "am_puck"]
    for voice in selected:
        if voice not in voices:
            print(f"Skipping unknown voice: {voice}", file=sys.stderr)
            continue
        print(f"Playing {voice}")
        wav = synthesize(config, voice, args.text)
        try:
            play(config, wav)
        finally:
            wav.unlink(missing_ok=True)

    choice = input("Choose one of those voices to save, or press Enter to keep current: ").strip()
    if choice:
        if choice not in voices:
            raise SystemExit(f"Unknown voice: {choice}")
        config.setdefault("tts", {})["voice"] = choice
        save_config(config)
        print(f"Configured tts.voice: {choice}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
