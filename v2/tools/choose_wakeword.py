#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import openwakeword
import yaml
from openwakeword.utils import download_models


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config.yaml"
EXAMPLE = ROOT / "config.example.yaml"


def load_config() -> dict[str, Any]:
    if not CONFIG.exists():
        CONFIG.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}


def save_config(config: dict[str, Any]) -> None:
    CONFIG.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def official_model_path(name: str) -> Path:
    info = openwakeword.MODELS.get(name)
    if not info:
        choices = ", ".join(sorted(openwakeword.MODELS))
        raise SystemExit(f"Unknown official wake word '{name}'. Choices: {choices}")
    return Path(info["model_path"].replace(".tflite", ".onnx"))


def list_models() -> None:
    print("Official OpenWakeWord pretrained models:")
    for name in sorted(openwakeword.MODELS):
        path = official_model_path(name)
        marker = "installed" if path.exists() else "available"
        print(f"  {name:12s} {marker:9s} {path}")


def set_official(name: str) -> None:
    if name not in openwakeword.MODELS:
        choices = ", ".join(sorted(openwakeword.MODELS))
        raise SystemExit(f"Unknown official wake word '{name}'. Choices: {choices}")
    download_models(model_names=[name])
    path = official_model_path(name)
    if not path.exists():
        raise SystemExit(f"Download finished but ONNX model is missing: {path}")
    config = load_config()
    wake = config.setdefault("wake_word", {})
    wake["enabled"] = True
    wake["pretrained"] = [name]
    wake["model_paths"] = []
    save_config(config)
    print(f"Wake word set to official model: {name}")


def set_custom(path_text: str) -> None:
    path = Path(path_text).expanduser()
    if not path.exists():
        raise SystemExit(f"Wake-word model does not exist: {path}")
    if path.suffix.lower() != ".onnx":
        raise SystemExit("Custom wake-word models must be ONNX files for this assistant.")
    config = load_config()
    wake = config.setdefault("wake_word", {})
    wake["enabled"] = True
    wake["pretrained"] = []
    wake["model_paths"] = [str(path)]
    save_config(config)
    print(f"Wake word set to custom ONNX model: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="List or configure OpenWakeWord models.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--list", action="store_true", help="List official pretrained wake-word models.")
    group.add_argument("--set", metavar="NAME", help="Download and select an official pretrained model.")
    group.add_argument("--custom", metavar="PATH", help="Select a custom trained ONNX wake-word model.")
    args = parser.parse_args()

    if args.set:
        set_official(args.set)
    elif args.custom:
        set_custom(args.custom)
    else:
        list_models()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
