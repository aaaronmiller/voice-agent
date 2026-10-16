import argparse
import os
from src.config_manager import ConfigManager
from src.main import main as run_assistant
from setup_assistant import main as run_setup
from src.startup_manager import StartupManager
from src.persona_manager import PersonaManager

def list_voices():
    try:
        import pyttsx3
        engine = pyttsx3.init()
        voices = engine.getProperty('voices')
        for v in voices:
            print(f"ID: {v.id}, Name: {v.name}")
    except ImportError:
        print("pyttsx3 not installed.")

def set_config(key, value):
    config = ConfigManager()
    config.set(key, value)
    print(f"Set {key} to {value}")

def list_personas():
    pm = PersonaManager()
    print("Available Personas:", ", ".join(pm.list_personas()))

def main():
    parser = argparse.ArgumentParser(description="AAA Voice Assistant CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # setup
    parser_setup = subparsers.add_parser("setup", help="Run setup wizard")

    # run
    parser_run = subparsers.add_parser("run", help="Start the assistant")

    # config
    parser_config = subparsers.add_parser("config", help="Manage configuration")
    parser_config.add_argument("key", help="Config key")
    parser_config.add_argument("value", help="Config value")

    # voice
    parser_voice = subparsers.add_parser("voice", help="Manage TTS voices")
    parser_voice.add_argument("--list", action="store_true", help="List available voices")
    parser_voice.add_argument("--set", help="Set voice ID")

    # startup
    parser_startup = subparsers.add_parser("startup", help="Manage startup settings")
    parser_startup.add_argument("--enable", action="store_true", help="Enable start on boot")
    parser_startup.add_argument("--disable", action="store_true", help="Disable start on boot")

    # persona
    parser_persona = subparsers.add_parser("persona", help="Manage assistant persona")
    parser_persona.add_argument("--list", action="store_true", help="List personas")
    parser_persona.add_argument("--set", help="Set active persona")

    # calibrate
    parser_calibrate = subparsers.add_parser("calibrate", help="Calibrate silence threshold")

    # check
    parser_check = subparsers.add_parser("check", help="Verify configuration and services")

    args = parser.parse_args()

    if args.command == "setup":
        run_setup()
    elif args.command == "calibrate":
        try:
            from src.audio_recorder import AudioRecorder
            ar = AudioRecorder()
            threshold = ar.calibrate_silence()
            set_config("silence_threshold", threshold)
            print("Calibration saved.")
            ar.terminate()
        except Exception as e:
            print(f"Calibration failed: {e}")
    elif args.command == "check":
        print("Checking system configuration...")
        config = ConfigManager()

        # Check Audio
        try:
            import pyaudio
            p = pyaudio.PyAudio()
            if p.get_device_count() > 0:
                print("[OK] Microphone detected.")
            else:
                print("[FAIL] No microphone devices found.")
            p.terminate()
        except Exception as e:
            print(f"[FAIL] Audio check failed: {e}")

        # Check API Keys
        provider = config.get("api_provider", "openai")
        key = config.get("api_keys", {}).get(provider, "")
        if config.get("llm_backend") == "api":
            if key:
                print(f"[OK] API Key present for {provider}.")
                # Optional: Make a test call? Maybe too expensive/slow for quick check.
            else:
                print(f"[FAIL] No API Key found for {provider}.")

        # Check OpenClaw
        if config.get("llm_backend") == "openclaw":
            import requests
            url = config.get("openclaw_url")
            try:
                requests.get(url, timeout=2)
                # 404/405 is fine, means server is up. ConnectionError is bad.
                print("[OK] OpenClaw server reachable.")
            except Exception as e:
                print(f"[FAIL] OpenClaw server unreachable: {e}")

    elif args.command == "run":
        run_assistant()
    elif args.command == "config":
        set_config(args.key, args.value)
    elif args.command == "voice":
        if args.list:
            list_voices()
        if args.set:
            set_config("voice_id", args.set)
    elif args.command == "startup":
        app_name = "VoiceAssistant"
        script_path = os.path.abspath("src/main.py")
        if args.enable:
            StartupManager.enable_startup(app_name, script_path)
        elif args.disable:
            StartupManager.disable_startup(app_name)
    elif args.command == "persona":
        if args.list:
            list_personas()
        if args.set:
            set_config("persona", args.set)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
