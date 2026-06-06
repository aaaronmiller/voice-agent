#!/usr/bin/env python3
from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

try:
    import yaml
except ImportError:
    print("PyYAML is required. Run ./setup.sh first, then ./wizard.", file=sys.stderr)
    raise SystemExit(1)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config.yaml"
EXAMPLE = ROOT / "config.example.yaml"

CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
BOLD = "\033[1m"
RESET = "\033[0m"

TITLE = r"""
   ______     __              _   __          __
  / ____/____/ /_  ____      / | / /___  ____/ /__
 / __/ / ___/ __ \/ __ \    /  |/ / __ \/ __  / _ \
 / /___/ /__/ / / / /_/ /   / /|  / /_/ / /_/ /  __/
 /_____/\___/_/ /_/\____/   /_/ |_/\____/\__,_/\___/

         local wake word + Parakeet STT + Kokoro TTS
"""


def clear() -> None:
    if sys.stdout.isatty():
        os.system("clear")


def say(text: str = "") -> None:
    print(text)


def load_config() -> dict[str, Any]:
    if not CONFIG.exists():
        CONFIG.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}


def save_config(config: dict[str, Any]) -> None:
    CONFIG.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def prompt(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{YELLOW}{label}{suffix}:{RESET} ").strip()
    return value or default


def confirm(label: str, default: bool = False) -> bool:
    choice = "Y/n" if default else "y/N"
    value = input(f"{YELLOW}{label} [{choice}]:{RESET} ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes"}


def choose(label: str, options: list[tuple[str, str]]) -> str:
    say(f"{BOLD}{label}{RESET}")
    for idx, (_key, text) in enumerate(options, 1):
        say(f"  {idx}. {text}")
    while True:
        raw = prompt("Choose", "1")
        try:
            idx = int(raw)
        except ValueError:
            say(f"{RED}Enter a number.{RESET}")
            continue
        if 1 <= idx <= len(options):
            return options[idx - 1][0]
        say(f"{RED}Out of range.{RESET}")


def run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    say(f"{CYAN}$ {' '.join(command)}{RESET}")
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def configure_backend() -> None:
    config = load_config()
    llm = config.setdefault("llm", {})
    choice = choose(
        "Backend provider",
        [
            ("ollama", "Ollama local server"),
            ("openai-compatible", "OpenAI-compatible /v1/chat/completions"),
            ("hermes", "Hermes Agent API server"),
            ("odysseus", "Odysseus /api/v1/chat"),
            ("offline", "No backend, local commands and echo only"),
        ],
    )

    if choice == "offline":
        llm["provider"] = "ollama"
        llm["model"] = ""
        llm["base_url"] = "http://127.0.0.1:11434"
        llm["api_key"] = ""
    elif choice == "ollama":
        llm["provider"] = "ollama"
        llm["base_url"] = prompt("Ollama base URL", str(llm.get("base_url") or "http://127.0.0.1:11434"))
        llm["model"] = prompt("Model name, blank uses first installed model", str(llm.get("model") or ""))
        llm["api_key"] = ""
    elif choice == "openai-compatible":
        llm["provider"] = "openai-compatible"
        llm["base_url"] = prompt("Base URL without /chat/completions", str(llm.get("base_url") or "http://127.0.0.1:8080/v1"))
        llm["model"] = prompt("Model name", str(llm.get("model") or ""))
        llm["api_key"] = prompt("API key, blank if none", str(llm.get("api_key") or ""))
    elif choice == "hermes":
        llm["provider"] = "hermes"
        llm["base_url"] = prompt("Hermes API base URL", str(llm.get("base_url") or "http://127.0.0.1:8642/v1"))
        llm["model"] = prompt("Hermes model", str(llm.get("model") or "hermes-agent"))
        llm["api_key"] = prompt("Hermes API key, blank if none", str(llm.get("api_key") or ""))
    elif choice == "odysseus":
        llm["provider"] = "odysseus"
        llm["base_url"] = prompt("Odysseus app URL", str(llm.get("base_url") or "http://127.0.0.1:7000"))
        llm["model"] = prompt("Model override, blank for Odysseus default", str(llm.get("model") or ""))
        llm["api_key"] = prompt("Odysseus chat-scoped API token", str(llm.get("api_key") or ""))

    save_config(config)
    say(f"{GREEN}Saved backend configuration.{RESET}")


def configure_voice() -> None:
    if confirm("List installed Kokoro voices first?", True):
        run([sys.executable, "tools/choose_voice.py", "--list"])
    voices = prompt("Three voices to audition", "af_heart af_bella am_puck").split()
    run([sys.executable, "tools/choose_voice.py", "--voices", *voices])


def _load_avatar_characters() -> tuple[list[tuple[str, str]], dict[str, str]]:
    from avatar import build as build_avatar  # noqa: E402

    manifest = build_avatar._load_manifest(ROOT / "avatar")
    options: list[tuple[str, str]] = []
    mapping: dict[str, str] = {}
    for name in manifest.get("characters", {}):
        label = name.replace("raccoon-hacker", "Raccoon Hacker").replace("owl-wizard", "Owl Wizard").replace("axolotl-astronaut", "Axolotl Astronaut").replace("axolotl-helmet", "Axolotl Helmet").replace("raccoon-cyber", "Raccoon Cyber").replace("-", " ").title()
        options.append((name, label))
        mapping[label.lower()] = name
    return options, mapping


def configure_avatar() -> None:
    config = load_config()
    avatar = config.setdefault("avatar", {})

    if not confirm("Enable floating avatar (lip-synced)?", bool(avatar.get("enabled", False))):
        avatar["enabled"] = False
        save_config(config)
        say(f"{GREEN}Avatar disabled.{RESET}")
        return

    try:
        options, _mapping = _load_avatar_characters()
    except Exception as exc:
        say(f"{RED}Could not load avatar manifest: {exc}{RESET}")
        if not confirm("Continue without avatar selection?"):
            avatar["enabled"] = False
            save_config(config)
        return

    current_character = str(avatar.get("character") or options[0][0] if options else "")
    character_options = [(name, label) for name, label in options]
    selected = choose("Select avatar character", character_options)
    character = selected if selected else current_character

    if confirm("Preview avatar before saving?", True):
        try:
            run([sys.executable, "tools/avatar_smoke.py", character])
        except subprocess.CalledProcessError:
            say(f"{YELLOW}Preview failed for {character}.{RESET}")
            if not confirm("Continue with this character anyway?"):
                if not confirm("Pick a different character?"):
                    avatar["enabled"] = False
                    save_config(config)
                    return

                character = choose("Select avatar character", character_options)

    avatar["enabled"] = True
    avatar["character"] = character
    avatar["recognizer"] = prompt("Rhubarb recognizer (phonetic/pocketSphinx)", str(avatar.get("recognizer") or "phonetic"))
    avatar["extended_shapes"] = prompt("Extended mouth shapes (blank=none)", str(avatar.get("extended_shapes") or "GH")).strip() or "GH"
    avatar["rhubarb_path"] = prompt("Rhubarb path (blank=auto-detect)", str(avatar.get("rhubarb_path") or "")) or None

    if confirm("Run frame preprocessor for this character now?", True):
        try:
            run([sys.executable, "-m", "avatar.preprocess", character])
        except subprocess.CalledProcessError:
            say(f"{YELLOW}Preprocess failed. Ensure the source sprite sheet exists under avatar/sources.{RESET}")
            if not confirm("Save avatar config anyway?"):
                avatar["enabled"] = False
                save_config(config)
                return

    save_config(config)
    say(f"{GREEN}Saved avatar configuration.{RESET}")


def configure_wake_vad_hotkeys() -> None:
    config = load_config()
    wake = config.setdefault("wake_word", {})
    vad = config.setdefault("vad", {})
    barge = config.setdefault("barge_in", {})
    hotkeys = config.setdefault("hotkeys", {})

    mode = choose("Wake word mode", [("pretrained", "Official OpenWakeWord model"), ("custom", "Custom ONNX model"), ("disabled", "Disable wake word")])
    if mode == "pretrained":
        run([sys.executable, "tools/choose_wakeword.py", "--list"])
        name = prompt("Official wake word", str((wake.get("pretrained") or ["hey_jarvis"])[0]))
        run([sys.executable, "tools/choose_wakeword.py", "--set", name])
        config = load_config()
        wake = config.setdefault("wake_word", {})
        vad = config.setdefault("vad", {})
        barge = config.setdefault("barge_in", {})
        hotkeys = config.setdefault("hotkeys", {})
        wake["enabled"] = True
        wake["pretrained"] = [name]
        wake["model_paths"] = []
    elif mode == "custom":
        path = prompt("Path to custom OpenWakeWord ONNX model")
        wake["enabled"] = True
        wake["pretrained"] = []
        wake["model_paths"] = [path]
    else:
        wake["enabled"] = False

    wake["sensitivity"] = float(prompt("Wake sensitivity", str(wake.get("sensitivity", 0.35))))
    vad["speech_threshold"] = float(prompt("VAD speech threshold", str(vad.get("speech_threshold", 0.48))))
    vad["silence_seconds"] = float(prompt("Silence seconds", str(vad.get("silence_seconds", 0.85))))
    vad["rms_floor"] = int(float(prompt("RMS floor", str(vad.get("rms_floor", 350)))))
    barge["enabled"] = confirm("Enable barge-in", bool(barge.get("enabled", True)))
    barge["min_speech_seconds"] = float(prompt("Barge-in speech seconds", str(barge.get("min_speech_seconds", 0.22))))
    hotkeys["enabled"] = confirm("Enable terminal Enter hotkey", bool(hotkeys.get("enabled", True)))
    hotkeys["terminal_enter"] = bool(hotkeys["enabled"])

    save_config(config)
    say(f"{GREEN}Saved wake/VAD/hotkey configuration.{RESET}")


def platform_setup() -> None:
    system = platform.system().lower()
    if system == "darwin":
        default_hint = "macos-arm"
        options = [
            ("macos-arm", "macOS ARM (Apple Silicon)"),
            ("generic", "Generic setup.sh"),
        ]
    elif system == "windows":
        default_hint = "windows"
        options = [
            ("windows", "Native Windows"),
            ("wsl2", "WSL2 Ubuntu with WSLg audio"),
            ("fedora", "Fedora 43 / GNOME / PipeWire"),
            ("generic", "Generic setup.sh"),
        ]
    else:
        default_hint = "fedora" if "fedora" in (platform.version() + " " + platform.platform()).lower() else "generic"
        options = [
            ("fedora", "Fedora 43 / GNOME / PipeWire"),
            ("wsl2", "WSL2 Ubuntu with WSLg audio"),
            ("windows", "Native Windows"),
            ("generic", "Generic setup.sh"),
        ]
    choice = choose(f"Platform setup ({default_hint} detected)", options)
    if choice == "fedora":
        run(["./install-fedora"])
    elif choice == "wsl2":
        run(["./install-wsl2"])
    elif choice == "windows":
        say("Run this from PowerShell:")
        say(r"  .\install-windows.ps1")
    elif choice == "macos-arm":
        say("Run the macOS installer:")
        say(r"  ./install-macos-arm")
        if confirm("Run it now?", True):
            run(["./install-macos-arm"])
    else:
        run(["./setup.sh"])


def install_launch_hotkey() -> None:
    system = platform.system().lower()
    if system == "windows":
        say("Run this from PowerShell:")
        say(r"  .\install-hotkey-windows.ps1")
        return
    run(["./install-hotkey-fedora"])


def record_wake_samples() -> None:
    phrase = prompt("Wake phrase to record", "hey codex")
    count = prompt("Sample count", "20")
    seconds = prompt("Seconds per sample", "2")
    run([sys.executable, "tools/record_wakeword_samples.py", phrase, "--count", count, "--seconds", seconds])


def main() -> int:
    actions: list[tuple[str, Callable[[], None]]] = [
        ("Run platform setup", platform_setup),
        ("Configure backend provider", configure_backend),
        ("Choose Kokoro voice", configure_voice),
        ("Configure avatar selection and lip-sync", configure_avatar),
        ("Tune wake word, VAD, barge-in, and hotkeys", configure_wake_vad_hotkeys),
        ("Record custom wake-word samples", record_wake_samples),
        ("Install launch hotkey", install_launch_hotkey),
        ("Run test suite", lambda: run(["./test.sh"])),
        ("Launch assistant", lambda: run(["./run.sh"])),
    ]

    while True:
        clear()
        say(CYAN + TITLE + RESET)
        for idx, (label, _action) in enumerate(actions, 1):
            say(f"  {idx}. {label}")
        say("  0. Exit")
        raw = prompt("Select", "0")
        if raw == "0":
            return 0
        try:
            idx = int(raw) - 1
            label, action = actions[idx]
        except (ValueError, IndexError):
            say(f"{RED}Invalid selection.{RESET}")
            input("Press Enter...")
            continue
        clear()
        say(f"{BOLD}{label}{RESET}")
        try:
            action()
        except subprocess.CalledProcessError as exc:
            say(f"{RED}Command failed with exit code {exc.returncode}.{RESET}")
        except KeyboardInterrupt:
            say()
            say(f"{YELLOW}Cancelled.{RESET}")
        input("Press Enter...")


if __name__ == "__main__":
    raise SystemExit(main())
