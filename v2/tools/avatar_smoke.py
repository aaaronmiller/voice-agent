#!/usr/bin/env python3
"""End-to-end smoke test for the avatar pipeline.

Bypasses the mic/STT/LLM stack: synthesises a short phrase with espeak-ng,
runs the avatar controller against it, and confirms Rhubarb produces visemes
and the sidecar comes up. Intended for local dev verification only.

Usage:
    .venv/bin/python tools/avatar_smoke.py [character]
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from avatar import build as build_avatar  # noqa: E402


def main() -> int:
    if shutil.which("espeak-ng") is None:
        print("espeak-ng missing; install it or wire to your TTS of choice", file=sys.stderr)
        return 1

    character = sys.argv[1] if len(sys.argv) > 1 else "raccoon-hacker"

    fd, name = tempfile.mkstemp(prefix="avatar-smoke-", suffix=".wav")
    wav = Path(name)
    try:
        subprocess.check_call(
            ["espeak-ng", "-w", str(wav), "Aye, the avatar is wired and the mouth moves with my words."]
        )

        ctrl = build_avatar({"enabled": True, "character": character})
        if not hasattr(ctrl, "process") or getattr(ctrl, "process", None) is None:
            print(f"avatar controller is null: {getattr(ctrl, 'reason', 'unknown')}")
            return 2

        print(f"[smoke] preload (rhubarb) on {wav.name}…")
        t0 = time.perf_counter()
        ok = ctrl.preload(wav)
        print(f"[smoke] preload returned {ok} in {time.perf_counter() - t0:.2f}s")
        if not ok:
            ctrl.shutdown()
            return 3

        print("[smoke] play cues + play wav in parallel for 3.5s")
        ctrl.play()
        # Pretend playback for the WAV duration so the sidecar has time to animate.
        time.sleep(3.0)
        ctrl.stop()
        time.sleep(0.5)
        ctrl.shutdown()
        print("[smoke] OK")
        return 0
    finally:
        wav.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
