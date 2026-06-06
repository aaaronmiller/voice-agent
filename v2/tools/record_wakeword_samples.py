#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import time
import wave
from pathlib import Path
from typing import Any

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.yaml"


def load_config() -> dict[str, Any]:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}


def save_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(audio.astype(np.int16).tobytes())


def record_alsa(config: dict[str, Any], seconds: float) -> np.ndarray:
    audio = config["audio"]
    sample_rate = int(audio["sample_rate"])
    duration_seconds = str(max(1, int(seconds + 0.999)))
    command = [
        "arecord",
        "-q",
        "-D",
        audio.get("arecord_device", "default"),
        "-f",
        "S16_LE",
        "-c",
        "1",
        "-r",
        str(sample_rate),
        "-t",
        "raw",
        "-d",
        duration_seconds,
    ]
    raw = subprocess.check_output(command)
    return np.frombuffer(raw, dtype=np.int16).copy()


def record_sounddevice(config: dict[str, Any], seconds: float) -> np.ndarray:
    import sounddevice as sd

    audio = config["audio"]
    sample_rate = int(audio["sample_rate"])
    data = sd.rec(
        int(sample_rate * seconds),
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
        device=audio.get("input_device"),
    )
    sd.wait()
    return np.asarray(data[:, 0], dtype=np.int16).copy()


def main() -> int:
    parser = argparse.ArgumentParser(description="Record positive custom wake-word samples.")
    parser.add_argument("phrase", help="Wake phrase label, e.g. hey-codex")
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--seconds", type=float, default=2.0)
    parser.add_argument("--out", default=str(ROOT / "wakeword_samples"))
    args = parser.parse_args()

    config = load_config()
    backend = config.get("audio", {}).get("backend", "alsa")
    label = args.phrase.strip().lower().replace(" ", "-")
    out_dir = Path(args.out) / label
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Recording {args.count} samples for '{args.phrase}'.")
    print("Say the wake phrase naturally after each countdown.")
    for i in range(1, args.count + 1):
        input(f"[{i}/{args.count}] Press Enter, then speak '{args.phrase}'...")
        time.sleep(0.25)
        if backend == "sounddevice":
            audio = record_sounddevice(config, args.seconds)
        else:
            audio = record_alsa(config, args.seconds)
        path = out_dir / f"{label}-{i:03d}.wav"
        save_wav(path, audio, int(config["audio"]["sample_rate"]))
        print(f"Saved {path}")

    print()
    print("Samples recorded. Use OpenWakeWord's official training notebook or trainer")
    print("to produce an ONNX model, then set wake_word.model_paths in config.yaml.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
