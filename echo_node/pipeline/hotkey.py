"""
Echo-Node Pipeline Hotkey — keyboard trigger listener.
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import time
from typing import Any


class KeyboardHotkey:
    """Listens for keyboard events in a background thread.
    Supports Escape key to toggle listening, and terminal Enter.
    """

    def __init__(self, config: dict[str, Any]):
        self.enabled = bool(config.get("enabled", True))
        self.terminal_enter = bool(config.get("terminal_enter", True))
        self.escape_enabled = bool(config.get("escape_toggle", True))
        self.events: queue.Queue[str] = queue.Queue()
        # Non-consuming interrupt flag for use during playback
        self._interrupt_flag = threading.Event()
        self.stop = False
        self._thread: threading.Thread | None = None
        self._listener_thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.enabled:
            return
        # Terminal Enter listener (always works)
        if self.terminal_enter:
            self._thread = threading.Thread(target=self._stdin_reader, name="hotkey-enter", daemon=True)
            self._thread.start()
        # Escape key listener (Linux: /dev/input, macOS: pynput)
        if self.escape_enabled:
            self._listener_thread = threading.Thread(target=self._escape_listener, name="hotkey-escape", daemon=True)
            self._listener_thread.start()

    def triggered(self) -> bool:
        """Consumes and returns one event from the queue. Used by main loop."""
        try:
            self.events.get_nowait()
            self._interrupt_flag.clear()
            return True
        except queue.Empty:
            return False

    def interrupt_requested(self) -> bool:
        """Non-consuming peek — used by playback loops to check for interrupt."""
        return self._interrupt_flag.is_set()

    def close(self) -> None:
        self.stop = True

    def _stdin_reader(self) -> None:
        """Read Enter from stdin (works in any terminal)."""
        while not self.stop:
            try:
                line = sys.stdin.readline()
            except Exception:
                return
            if line == "":
                return
            self.events.put("enter")
            self._interrupt_flag.set()

    def _escape_listener(self) -> None:
        """Listen for Escape key press. Linux, macOS, Windows."""
        if sys.platform == "linux":
            self._escape_linux()
        elif sys.platform == "darwin":
            self._escape_pynput()
        elif sys.platform == "win32":
            self._escape_pynput()

    def _escape_pynput(self) -> None:
        """Cross-platform Escape listener via pynput (macOS, Windows)."""
        try:
            from pynput import keyboard as _kb
            def on_press(key):
                if not self.stop and key == _kb.Key.esc:
                    self.events.put("escape")
            with _kb.Listener(on_press=on_press) as listener:
                listener.join()
        except ImportError:
            pass  # pynput not installed, Escape unavailable

    def _escape_linux(self) -> None:
        """Read raw keyboard events from /dev/input for Escape key.

        A single physical keyboard often appears on multiple ``/dev/input/event*``
        devices (e.g. event3 + event4), so we deduplicate with a time-based
        debounce: an Escape press within 250ms of the previous one is dropped.
        """
        import glob
        keyboards = glob.glob("/dev/input/event*")
        if not keyboards:
            return

        _last_esc = [0.0]  # mutable shared state across threads

        def _read_device(path: str) -> None:
            try:
                with open(path, "rb") as f:
                    while not self.stop:
                        event = f.read(16)
                        if not event or len(event) < 16:
                            break
                        import struct
                        _, _, ev_type, ev_code, ev_value = struct.unpack("=llHHi", event)
                        if ev_type == 1 and ev_code == 1 and ev_value == 1:
                            now = time.monotonic()
                            if now - _last_esc[0] > 0.25:
                                _last_esc[0] = now
                                self.events.put("escape")
            except (PermissionError, OSError, FileNotFoundError):
                pass

        for device in keyboards:
            threading.Thread(target=_read_device, args=(device,), daemon=True).start()

    def _escape_macos(self) -> None:
        """macOS Escape listener via pynput."""
        self._escape_pynput()


# ── Native integration adapters ─────────────────────────────────────