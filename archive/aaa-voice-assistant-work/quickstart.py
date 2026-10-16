#!/usr/bin/env python3
"""
Unified Quickstart Script for Voice Assistant
Detects OS, checks dependencies, runs setup, and starts the assistant.
"""

import sys
import os
import subprocess
import platform
import shutil
import time

# Import setup logic directly to unify experience
try:
    from setup_assistant import main as run_setup_wizard
except ImportError:
    # If not in path, try adding current dir
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from setup_assistant import main as run_setup_wizard

def check_command(cmd):
    return shutil.which(cmd) is not None

def install_system_dependencies():
    system = platform.system()
    if system == "Linux":
        print("Checking Linux system dependencies...")
        # Check for apt-get (Debian/Ubuntu)
        if check_command("apt-get"):
            # Check for portaudio and xclip (for clipboard)
            pkgs = []
            if not check_command("xclip") and not check_command("xsel"):
                pkgs.append("xclip")

            # Check for portaudio headers (tricky to check directly, assume needed if pyaudio fails)
            # But let's be proactive
            try:
                import pyaudio
            except ImportError:
                # likely need portaudio19-dev
                pkgs.append("portaudio19-dev")
                pkgs.append("python3-dev")

            if pkgs:
                print(f"Missing system packages: {', '.join(pkgs)}")
                choice = input("Install them with sudo apt-get? (y/n): ").lower()
                if choice == 'y':
                    subprocess.check_call(["sudo", "apt-get", "update"])
                    subprocess.check_call(["sudo", "apt-get", "install", "-y"] + pkgs)
    elif system == "Darwin":
        print("Checking macOS system dependencies...")
        if check_command("brew"):
            pkgs = []
            if not check_command("portaudio"):
                pkgs.append("portaudio")

            if pkgs:
                print(f"Missing brew packages: {', '.join(pkgs)}")
                choice = input("Install them with brew? (y/n): ").lower()
                if choice == 'y':
                    subprocess.check_call(["brew", "install"] + pkgs)
        else:
            print("Homebrew not found. Please install portaudio manually if PyAudio fails.")

def main():
    print("=== AAA Voice Assistant Quickstart ===")

    # 1. Check Python version
    if sys.version_info < (3, 8):
        print("Error: Python 3.8+ is required.")
        sys.exit(1)

    # 2. Check basic tools
    if not check_command("git"):
        print("Error: git is required.")
        sys.exit(1)

    if not check_command("cmake"):
        print("Warning: cmake not found. Whisper.cpp build might fail.")
        print("Press Enter to continue anyway...")
        input()

    # 3. Install System Dependencies (Linux/Mac)
    install_system_dependencies()

    # Warning for Linux users regarding 'keyboard'
    if platform.system() == "Linux" and os.geteuid() != 0:
        print("\n[WARNING] On Linux, the 'keyboard' library requires root privileges to intercept global hotkeys.")
        print("You may need to run this script with 'sudo python quickstart.py' or configure udev rules.")
        print("Continuing, but hotkeys might fail...\n")
        time.sleep(2)

    # 4. Run Setup Assistant
    print("\n--- Running Setup Wizard ---")
    try:
        run_setup_wizard()
    except Exception as e:
        print(f"Setup failed: {e}")
        sys.exit(1)

    # 5. Start Assistant
    print("\n--- Starting Assistant ---")
    try:
        # Import main here to avoid import errors before setup
        from src.main import main as run_assistant
        run_assistant()
    except ImportError as e:
         print(f"Failed to import assistant: {e}")
    except KeyboardInterrupt:
        print("\nExiting.")

if __name__ == "__main__":
    main()
