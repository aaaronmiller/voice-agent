"""In-process avatar controller.

Owns a long-lived sidecar (``v2/avatar/window.py``) and runs Rhubarb against
each TTS WAV to ship viseme timing into the floating window in sync with
playback.

Designed to fail safe: if PyQt6 is missing, if Rhubarb is missing, or if the
sidecar dies, the controller falls back to a no-op so the assistant keeps
talking without an avatar.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

import soundfile as sf

_BASE = Path(__file__).resolve().parent
_FRAMES_ROOT = _BASE / "frames"
_VENDOR_RHUBARB = _BASE.parent / "vendor" / "rhubarb" / "rhubarb"


def _resolve_rhubarb(configured: str | None) -> str | None:
    if configured:
        p = Path(configured).expanduser()
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    if _VENDOR_RHUBARB.is_file() and os.access(_VENDOR_RHUBARB, os.X_OK):
        return str(_VENDOR_RHUBARB)
    found = shutil.which("rhubarb")
    return found


class NullAvatar:
    """No-op controller. Used when the avatar is disabled or unavailable."""

    def __init__(self, reason: str = "disabled") -> None:
        self.reason = reason

    def preload(self, wav_path: Path) -> bool:
        return False

    def play(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def shutdown(self) -> None:
        pass


class AvatarController:
    """Live avatar controller. Spawns the PyQt6 sidecar and ships viseme cues
    derived from each TTS WAV.
    """

    def __init__(self, config: dict[str, Any]):
        self.enabled = bool(config.get("enabled", False))
        self.character = str(config.get("character") or "raccoon-hacker")
        self.recognizer = str(config.get("recognizer", "phonetic"))
        self.extended_shapes = str(config.get("extended_shapes", "GH"))
        self.rhubarb_path = _resolve_rhubarb(config.get("rhubarb_path"))
        self.python_executable = sys.executable
        self.process: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._pending: dict | None = None

        if not self.enabled:
            return
        if self.rhubarb_path is None:
            print("[avatar] disabled: rhubarb binary not found", flush=True)
            self.enabled = False
            return
        if not (_FRAMES_ROOT / self.character).is_dir():
            print(
                f"[avatar] disabled: no frames for character {self.character!r}. "
                f"Run `python -m avatar.preprocess` first.",
                flush=True,
            )
            self.enabled = False
            return
        try:
            self._spawn_sidecar()
        except Exception as exc:
            print(f"[avatar] disabled: sidecar spawn failed: {exc}", flush=True)
            self.enabled = False
            self.process = None

    # -- sidecar management --------------------------------------------------

    def _spawn_sidecar(self) -> None:
        cmd = [
            self.python_executable,
            "-m",
            "avatar.window",
            "--character",
            self.character,
        ]
        env = dict(os.environ)
        # Force the Qt Wayland platform when available; X11 fallback is automatic.
        env.setdefault("QT_QPA_PLATFORM", "wayland;xcb")
        env.setdefault("PYTHONUNBUFFERED", "1")
        self.process = subprocess.Popen(
            cmd,
            cwd=str(_BASE.parent),
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            text=True,
            bufsize=1,
        )
        print(f"[avatar] sidecar started pid={self.process.pid} character={self.character}", flush=True)

    def _send(self, payload: dict) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        try:
            assert self.process.stdin is not None
            self.process.stdin.write(json.dumps(payload) + "\n")
            self.process.stdin.flush()
        except (BrokenPipeError, ValueError):
            self.enabled = False

    # -- viseme extraction ---------------------------------------------------

    def _normalise_to_pcm16(self, wav_path: Path) -> Path:
        """Rhubarb is happiest with 16-bit PCM WAV at 16 kHz mono.

        We always rewrite via soundfile to guarantee that, regardless of what
        the TTS backend emitted (Kokoro is float32 @ 24 kHz, espeak is PCM16
        @ 22 kHz).
        """
        data, sr = sf.read(str(wav_path), always_2d=False)
        if data.ndim > 1:
            data = data.mean(axis=1)
        fd, tmp = tempfile.mkstemp(prefix="avatar-pcm16-", suffix=".wav")
        os.close(fd)
        sf.write(tmp, data, sr, subtype="PCM_16")
        return Path(tmp)

    def preload(self, wav_path: Path, offset_seconds: float = 0.0) -> bool:
        """Run Rhubarb on ``wav_path`` and buffer the resulting cue list.
        Returns True when cues are queued and play() will animate; False on
        any failure (caller proceeds with audio anyway).
        """
        if not self.enabled or self.rhubarb_path is None:
            return False
        pcm16: Path | None = None
        try:
            pcm16 = self._normalise_to_pcm16(wav_path)
            cmd = [
                self.rhubarb_path,
                "-f", "json",
                "-r", self.recognizer,
                "--quiet",
            ]
            if self.extended_shapes:
                cmd.extend(["--extendedShapes", self.extended_shapes])
            cmd.append(str(pcm16))
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                return False
            data = json.loads(result.stdout)
            cues = data.get("mouthCues") or []
            duration = float((data.get("metadata") or {}).get("duration") or 0.0)
            if not cues:
                return False
            with self._lock:
                self._pending = {"cmd": "play", "cues": cues, "duration": duration}
                if offset_seconds > 0:
                    self._pending["start_offset"] = float(offset_seconds)
            return True
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
            return False
        finally:
            if pcm16 is not None:
                try:
                    pcm16.unlink()
                except OSError:
                    pass

    def play(self) -> None:
        with self._lock:
            payload = self._pending
            self._pending = None
        if payload is not None:
            self._send(payload)

    def stop(self) -> None:
        self._send({"cmd": "stop"})

    def set_character(self, name: str) -> None:
        if not name:
            return
        self.character = name
        self._send({"cmd": "set_character", "name": name})

    def shutdown(self) -> None:
        if self.process is None:
            return
        try:
            self._send({"cmd": "quit"})
        finally:
            try:
                self.process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    self.process.kill()
            self.process = None


def build(config: dict[str, Any]):
    """Factory: return an AvatarController when enabled, NullAvatar otherwise."""
    if not config.get("enabled"):
        return NullAvatar("config disabled")
    ctrl = AvatarController(config)
    if not ctrl.enabled:
        return NullAvatar("init failed")
    return ctrl
