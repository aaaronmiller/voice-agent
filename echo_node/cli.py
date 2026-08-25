#!/usr/bin/env python3
"""
Echo-Node Unified CLI — single entry point for all frontends.

Usage:
  echo-node --web               # Launch web frontend (opens browser)
  echo-node --tui               # Launch TUI frontend
  echo-node --voice-mode        # Legacy voice-only mode (local STT→LLM→TTS)
  echo-node --monitor           # Launch latency dashboard
  echo-node --gateway-only      # Start only the gateway server
  echo-node --gemini-live       # Gemini Live standalone CLI
  echo-node --openai-realtime   # OpenAI Realtime standalone CLI

  # Provider override (for --web and --tui):
  echo-node --tui --provider gemini-live

  # Env var overrides:
  ECHO_DEFAULT_PROVIDER=gemini-live ECHO_GATEWAY_URL=ws://localhost:3000/ws echo-node --web

Feature parity across all modes:
  - Every mode supports --provider and --config
  - Every mode reads the same env vars (GEMINI_API_KEY, OPENAI_API_KEY, etc.)
  - Every mode prints latency metrics after each turn
  - Every mode supports Ctrl+C to quit
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import NoReturn

ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = ROOT / ".venv" / "bin" / "python3"
SYSTEM_PYTHON = sys.executable or "python3"


def _python() -> str:
    """Return the Python interpreter, preferring venv."""
    return str(VENV_PYTHON) if VENV_PYTHON.exists() else SYSTEM_PYTHON


def _bun() -> str:
    """Return the Bun executable."""
    return shutil_which("bun") or "bun"


def shutil_which(cmd: str) -> str | None:
    """Find an executable."""
    import shutil
    return shutil.which(cmd)


def start_gateway() -> subprocess.Popen:
    """Start the gateway server in the background."""
    gateway_dir = ROOT / "gateway"
    if not (gateway_dir / "src" / "index.ts").exists():
        print("[gateway] not found at expected path, skipping auto-start")
        return None

    proc = subprocess.Popen(
        [_bun(), "run", "src/index.ts"],
        cwd=gateway_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    print(f"[gateway] starting (pid {proc.pid})...")
    return proc


def cmd_web(args: argparse.Namespace) -> NoReturn:
    """Launch web frontend."""
    gateway = start_gateway()
    frontend_dir = ROOT / "frontend"
    if not (frontend_dir / "package.json").exists():
        print("[web] frontend/ not set up. Run: cd frontend && bun install")
        sys.exit(1)

    print("[web] starting dev server...")
    env = os.environ.copy()
    if args.provider:
        env["ECHO_DEFAULT_PROVIDER"] = args.provider

    try:
        proc = subprocess.Popen(
            [_bun(), "run", "dev"],
            cwd=frontend_dir,
            env=env,
        )
        webbrowser.open("http://localhost:5173")
        proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if gateway:
            gateway.terminate()
    sys.exit(0)


def cmd_tui(args: argparse.Namespace) -> NoReturn:
    """Launch TUI frontend."""
    gateway = start_gateway()
    tui_dir = ROOT / "tui"

    env = os.environ.copy()
    if args.provider:
        env["ECHO_DEFAULT_PROVIDER"] = args.provider
    if args.url:
        env["ECHO_GATEWAY_URL"] = args.url

    cmd = [_python(), "-m", "echo_tui"]
    if args.provider:
        cmd.extend(["--provider", args.provider])
    if args.url:
        cmd.extend(["--url", args.url])

    try:
        subprocess.run(cmd, cwd=tui_dir, env=env)
    except KeyboardInterrupt:
        pass
    finally:
        if gateway:
            gateway.terminate()
    sys.exit(0)


def cmd_voice(args: argparse.Namespace) -> NoReturn:
    """Legacy voice-only mode. Uses the existing assistant_v2.py."""
    v2_dir = ROOT / "v2"
    assistant_py = v2_dir / "assistant_v2.py"

    if not assistant_py.exists():
        print("[voice] assistant_v2.py not found")
        sys.exit(1)

    env = os.environ.copy()
    if args.provider:
        env["ECHO_LLM_PROVIDER"] = args.provider

    cmd = [_python(), str(assistant_py)]
    if args.config:
        cmd.extend(["--config", args.config])

    try:
        subprocess.run(cmd, cwd=v2_dir, env=env)
    except KeyboardInterrupt:
        pass
    sys.exit(0)


def cmd_monitor(args: argparse.Namespace) -> NoReturn:
    """Launch the monitoring dashboard."""
    tui_dir = ROOT / "tui"

    cmd = [_python(), "-m", "echo_monitor"]
    if args.url:
        cmd.extend(["--url", args.url])
    if args.history:
        cmd.append("--history")

    try:
        subprocess.run(cmd, cwd=tui_dir)
    except KeyboardInterrupt:
        pass
    sys.exit(0)


def cmd_gateway(args: argparse.Namespace) -> NoReturn:
    """Start only the gateway server."""
    gateway = start_gateway()
    try:
        gateway.wait()
    except KeyboardInterrupt:
        gateway.terminate()
    sys.exit(0)


def cmd_gemini_live(args: argparse.Namespace) -> NoReturn:
    """Launch Gemini Live standalone CLI."""
    import importlib.util
    import sys as _sys
    v2_providers = ROOT / "v2" / "providers"
    _sys.path.insert(0, str(v2_providers.parent))
    spec = importlib.util.spec_from_file_location("gemini_live", v2_providers / "gemini_live.py")
    if spec and spec.loader:
        gl = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gl)
        _sys.argv = ["echo-node", "--gemini-live"]
        if args.model:
            _sys.argv.extend(["--model", args.model])
        if args.voice_name:
            _sys.argv.extend(["--voice", args.voice_name])
        gl.main()
    else:
        print("[error] gemini_live.py not found at v2/providers/gemini_live.py")
    sys.exit(0)


def cmd_openai_realtime(args: argparse.Namespace) -> NoReturn:
    """Launch OpenAI Realtime standalone CLI."""
    import importlib.util
    import sys as _sys
    v2_providers = ROOT / "v2" / "providers"
    _sys.path.insert(0, str(v2_providers.parent))
    spec = importlib.util.spec_from_file_location("openai_realtime", v2_providers / "openai_realtime.py")
    if spec and spec.loader:
        or_ = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(or_)
        _sys.argv = ["echo-node", "--openai-realtime"]
        if args.voice_name:
            _sys.argv.extend(["--voice", args.voice_name])
        or_.main()
    else:
        print("[error] openai_realtime.py not found at v2/providers/")
    sys.exit(0)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Echo-Node Voice Agent — Unified CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment variables:
  ECHO_DEFAULT_PROVIDER    Default provider (gemini-live, openai-realtime, hermes, etc.)
  ECHO_GATEWAY_URL         Gateway WebSocket URL (default: ws://127.0.0.1:3000/ws)
  GEMINI_API_KEY           Google Gemini API key
  OPENAI_API_KEY           OpenAI API key
  ECHO_LLM_PROVIDER        LLM provider override (for --voice mode)

Examples:
  echo-node --tui --provider gemini-live
  ECHO_DEFAULT_PROVIDER=openai-realtime echo-node --web
  echo-node --gemini-live --voice Puck
        """,
    )

    parser.add_argument("--web", action="store_true", help="Launch web frontend")
    parser.add_argument("--tui", action="store_true", help="Launch TUI frontend")
    parser.add_argument("--voice-mode", action="store_true", help="Legacy voice-only mode (local STT→LLM→TTS)")
    parser.add_argument("--monitor", action="store_true", help="Launch monitoring dashboard")
    parser.add_argument("--gateway-only", action="store_true", help="Start only the gateway server")
    parser.add_argument("--gemini-live", action="store_true", help="Gemini Live standalone CLI")
    parser.add_argument("--openai-realtime", action="store_true", help="OpenAI Realtime standalone CLI")

    parser.add_argument("--provider", default=os.environ.get("ECHO_DEFAULT_PROVIDER", ""),
                        help="Provider to use (for --web, --tui)")
    parser.add_argument("--url", default=os.environ.get("ECHO_GATEWAY_URL", "ws://127.0.0.1:3000/ws"),
                        help="Gateway WebSocket URL")
    parser.add_argument("--config", default="", help="Config file path (for --voice)")
    parser.add_argument("--history", action="store_true", help="Replay last session (for --monitor)")

    # Gemini Live / OpenAI Realtime options
    parser.add_argument("--model", default=os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-live-preview"),
                        help="Model name (for --gemini-live)")
    parser.add_argument("--voice", dest="voice_name",
                        default=os.environ.get("GEMINI_VOICE", "Puck"),
                        help="Voice name (for --gemini-live, --openai-realtime)")

    args = parser.parse_args()

    # Route to the right mode
    if args.web:
        cmd_web(args)
    elif args.tui:
        cmd_tui(args)
    elif args.voice_mode:
        cmd_voice(args)
    elif args.monitor:
        cmd_monitor(args)
    elif args.gateway_only:
        cmd_gateway(args)
    elif args.gemini_live:
        cmd_gemini_live(args)
    elif args.openai_realtime:
        cmd_openai_realtime(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
