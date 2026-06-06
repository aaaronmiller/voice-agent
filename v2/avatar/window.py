"""Floating avatar window — runs as its own process to keep the Qt event loop
clear of the assistant's audio/STT loops.

Protocol (line-delimited JSON on stdin, one object per line):

    {"cmd":"set_character", "name":"raccoon-hacker"}
    {"cmd":"play", "cues":[{"start":0.0,"end":0.06,"value":"B"}, ...], "duration":2.6}
    {"cmd":"stop"}
    {"cmd":"show"}
    {"cmd":"hide"}
    {"cmd":"quit"}

Run directly for a quick preview:

    .venv/bin/python -m v2.avatar.window --character raccoon-hacker --demo
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import yaml
from PyQt6.QtCore import QObject, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QGuiApplication, QPixmap
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

VISEMES: tuple[str, ...] = ("X", "A", "B", "C", "D", "E", "F", "G", "H")
DEFAULT_SIZE = 220        # max edge in px on screen
MARGIN = 24               # distance from screen corner
IDLE_BLINK_PERIOD_S = 4.5  # X swaps to A briefly for an idle "blink" feel


class StdinReader(QThread):
    """Reads line-JSON commands from stdin and emits them on the Qt thread."""

    command = pyqtSignal(dict)

    def run(self) -> None:  # noqa: D401
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                self.command.emit(payload)


class AvatarWindow(QWidget):
    def __init__(self, frames_root: Path, manifest: dict, default_character: str) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self.frames_root = frames_root
        self.manifest = manifest
        self.character: str = ""
        self.frames: dict[str, QPixmap] = {}

        self.label = QLabel(self)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.label.setStyleSheet("background: transparent;")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.resize(DEFAULT_SIZE, DEFAULT_SIZE)
        self.label.resize(DEFAULT_SIZE, DEFAULT_SIZE)

        # Playback state
        self._cues: list[dict] = []
        self._play_start_monotonic: float = 0.0
        self._duration: float = 0.0
        self._cue_index: int = 0
        self._playing: bool = False

        self._tick = QTimer(self)
        self._tick.setInterval(16)  # ~60 fps
        self._tick.timeout.connect(self._on_tick)

        self._idle_blink = QTimer(self)
        self._idle_blink.setInterval(int(IDLE_BLINK_PERIOD_S * 1000))
        self._idle_blink.timeout.connect(self._idle_blink_tick)

        self.set_character(default_character)
        self._anchor_bottom_right()
        self._show_viseme("X")

    # -- positioning ---------------------------------------------------------

    def _anchor_bottom_right(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.x() + geo.width() - self.width() - MARGIN
        y = geo.y() + geo.height() - self.height() - MARGIN
        self.move(x, y)

    # -- character loading ---------------------------------------------------

    def set_character(self, name: str) -> None:
        if name == self.character and self.frames:
            return
        char_dir = self.frames_root / name
        if not char_dir.is_dir():
            print(f"[avatar-window] unknown character: {name}", file=sys.stderr, flush=True)
            return
        loaded: dict[str, QPixmap] = {}
        for viseme in VISEMES:
            path = char_dir / f"{viseme}.png"
            if not path.exists():
                print(f"[avatar-window] missing frame {path}", file=sys.stderr, flush=True)
                continue
            pix = QPixmap(str(path))
            if pix.isNull():
                print(f"[avatar-window] failed to load {path}", file=sys.stderr, flush=True)
                continue
            loaded[viseme] = pix.scaled(
                DEFAULT_SIZE,
                DEFAULT_SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        if not loaded:
            return
        self.character = name
        self.frames = loaded
        self._show_viseme("X")

    # -- viseme rendering ----------------------------------------------------

    def _show_viseme(self, viseme: str) -> None:
        pix = self.frames.get(viseme) or self.frames.get("X")
        if pix is None:
            return
        # Center the (possibly smaller) pixmap inside the fixed window.
        canvas = QPixmap(self.size())
        canvas.fill(Qt.GlobalColor.transparent)
        from PyQt6.QtGui import QPainter

        painter = QPainter(canvas)
        x = (canvas.width() - pix.width()) // 2
        y = (canvas.height() - pix.height()) // 2
        painter.drawPixmap(x, y, pix)
        painter.end()
        self.label.setPixmap(canvas)

    # -- playback loop -------------------------------------------------------

    def start_play(self, cues: list[dict], duration: float) -> None:
        self._cues = sorted(cues, key=lambda c: float(c.get("start", 0.0)))
        self._duration = float(duration)
        self._cue_index = 0
        self._play_start_monotonic = time.monotonic()
        self._playing = True
        self._idle_blink.stop()
        self._tick.start()

    def stop_play(self) -> None:
        self._playing = False
        self._tick.stop()
        self._show_viseme("X")
        if not self._idle_blink.isActive():
            self._idle_blink.start()

    def _on_tick(self) -> None:
        if not self._playing:
            self._tick.stop()
            return
        t = time.monotonic() - self._play_start_monotonic
        if self._duration and t >= self._duration:
            self.stop_play()
            return
        # Walk cues; find the one whose [start,end) contains t.
        while self._cue_index < len(self._cues):
            cue = self._cues[self._cue_index]
            start = float(cue.get("start", 0.0))
            end = float(cue.get("end", start))
            if t < start:
                break
            if t < end:
                self._show_viseme(str(cue.get("value", "X")))
                return
            self._cue_index += 1
        # Past the last cue end but before duration → rest mouth.
        self._show_viseme("X")

    def _idle_blink_tick(self) -> None:
        if self._playing:
            return
        self._show_viseme("A")
        QTimer.singleShot(120, lambda: self._show_viseme("X") if not self._playing else None)


class CommandRouter(QObject):
    def __init__(self, window: AvatarWindow) -> None:
        super().__init__()
        self.window = window

    def on_command(self, payload: dict) -> None:
        cmd = payload.get("cmd")
        if cmd == "set_character":
            name = str(payload.get("name", "")).strip()
            if name:
                self.window.set_character(name)
        elif cmd == "play":
            cues = payload.get("cues") or []
            duration = float(payload.get("duration") or 0.0)
            if cues:
                self.window.show()
                self.window.start_play(list(cues), duration)
        elif cmd == "stop":
            self.window.stop_play()
        elif cmd == "show":
            self.window.show()
        elif cmd == "hide":
            self.window.hide()
        elif cmd == "quit":
            QApplication.instance().quit()


def _load_manifest(base: Path) -> dict:
    return yaml.safe_load((base / "characters.yaml").read_text())


def _demo_cues(duration: float = 3.5) -> list[dict]:
    """Build a synthetic viseme stream so we can preview without TTS."""
    cycle = ["A", "B", "C", "D", "E", "F", "B", "C", "G", "H", "X"]
    step = 0.18
    cues: list[dict] = []
    n = max(1, int(duration / step))
    for i in range(n):
        cues.append({"start": i * step, "end": (i + 1) * step, "value": cycle[i % len(cycle)]})
    return cues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--character", default=None)
    parser.add_argument("--demo", action="store_true", help="loop a synthetic viseme stream")
    args = parser.parse_args()

    base = Path(__file__).resolve().parent
    manifest = _load_manifest(base)
    default_character = args.character or manifest.get("default") or next(iter(manifest["characters"]))

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    window = AvatarWindow(base / "frames", manifest, default_character)
    window.show()

    router = CommandRouter(window)

    if args.demo:
        demo_timer = QTimer()
        demo_timer.setInterval(int(4.0 * 1000))
        demo_timer.timeout.connect(lambda: window.start_play(_demo_cues(), 3.5))
        demo_timer.start()
        window.start_play(_demo_cues(), 3.5)
    else:
        reader = StdinReader()
        reader.command.connect(router.on_command)
        reader.start()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
