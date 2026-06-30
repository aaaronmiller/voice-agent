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
from PyQt6.QtGui import (
    QAction,
    QFont,
    QGuiApplication,
    QIcon,
    QPainter,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

VISEMES: tuple[str, ...] = ("X", "A", "B", "C", "D", "E", "F", "G", "H")
DEFAULT_SIZE = 220         # max edge in px on screen
MARGIN = 16                # distance from screen corner
FRAME_PADDING = 48         # extra pixels for the border/controls around the avatar
IDLE_BLINK_PERIOD_S = 4.5

# ── Colours ─────────────────────────────────────────────────────────

FRAME_BG = "rgba(10, 10, 20, 0.60)"
FRAME_BORDER = "rgba(100, 180, 255, 0.30)"
BTN_BG = "rgba(60, 60, 90, 0.70)"
BTN_HOVER = "rgba(100, 180, 255, 0.40)"
BTN_STYLE = f"""
    QPushButton {{
        background: {BTN_BG};
        color: #ccd;
        border: 1px solid {FRAME_BORDER};
        border-radius: 10px;
        padding: 2px 6px;
        font-size: 11px;
        font-weight: bold;
        min-width: 22px;
        min-height: 22px;
    }}
    QPushButton:hover {{
        background: {BTN_HOVER};
        border: 1px solid rgba(150, 200, 255, 0.6);
    }}
"""


# ── Stdin reader thread ─────────────────────────────────────────────

class StdinReader(QThread):
    """Reads line-JSON commands from stdin and emits them on the Qt thread."""

    command = pyqtSignal(dict)

    def run(self) -> None:
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


# ── Settings popup ───────────────────────────────────────────────────

class SettingsPopup(QFrame):
    """Floating settings panel for avatar selection and size."""

    def __init__(self, parent: QWidget, character_list: list[str], current: str):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(f"""
            QFrame {{
                background: {FRAME_BG};
                border: 1px solid {FRAME_BORDER};
                border-radius: 12px;
                padding: 8px;
            }}
            QLabel {{
                color: #dde;
                font-size: 11px;
                font-weight: bold;
            }}
            QComboBox {{
                background: {BTN_BG};
                color: #dde;
                border: 1px solid {FRAME_BORDER};
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
                min-width: 120px;
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background: rgba(20, 20, 40, 0.95);
                color: #dde;
                selection-background-color: rgba(100, 180, 255, 0.3);
                border: 1px solid {FRAME_BORDER};
                border-radius: 4px;
            }}
            QSlider::groove:horizontal {{
                height: 4px;
                background: rgba(100, 100, 140, 0.5);
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: rgba(100, 180, 255, 0.8);
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("⚙ Avatar Settings")
        title.setStyleSheet("font-size: 13px; font-weight: bold; color: #eef;")
        layout.addWidget(title)

        # Character selector
        char_layout = QHBoxLayout()
        char_label = QLabel("Character:")
        char_layout.addWidget(char_label)

        self.combo = QComboBox()
        self.combo.addItems(character_list)
        self.combo.setCurrentText(current)
        self.combo.currentTextChanged.connect(self._on_char_changed)
        char_layout.addWidget(self.combo)
        layout.addLayout(char_layout)

        # Size slider
        size_layout = QHBoxLayout()
        size_label = QLabel("Size:")
        size_layout.addWidget(size_label)

        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(120, 400)
        self.size_slider.setValue(DEFAULT_SIZE)
        self.size_slider.valueChanged.connect(self._on_size_changed)
        size_layout.addWidget(self.size_slider)

        self.size_label = QLabel(f"{DEFAULT_SIZE}px")
        self.size_label.setStyleSheet("font-size: 10px; color: #aab; min-width: 35px;")
        size_layout.addWidget(self.size_label)
        layout.addLayout(size_layout)

        self.setLayout(layout)
        self.adjustSize()

    def _on_char_changed(self, name: str) -> None:
        parent = self.parent()
        if hasattr(parent, 'set_character'):
            parent.set_character(name)

    def _on_size_changed(self, value: int) -> None:
        self.size_label.setText(f"{value}px")
        parent = self.parent()
        if hasattr(parent, 'resize_avatar'):
            parent.resize_avatar(value)

    def show_at(self, x: int, y: int) -> None:
        self.move(x - self.width(), y - self.height())
        self.show()


# ── Main avatar window ──────────────────────────────────────────────

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
        self.character_list = list(manifest.get("characters", {}).keys())
        self.character: str = ""
        self.frames: dict[str, QPixmap] = {}
        self._avatar_size = DEFAULT_SIZE

        # Root layout — holds the frame + inner content
        self.setStyleSheet("background: transparent;")

        # Outer widget with the frame styling
        self.frame_widget = QFrame(self)
        self.frame_widget.setStyleSheet(f"""
            QFrame {{
                background: {FRAME_BG};
                border: 1.5px solid {FRAME_BORDER};
                border-radius: 16px;
            }}
        """)
        # Layout inside the frame
        frame_layout = QVBoxLayout(self.frame_widget)
        frame_layout.setContentsMargins(6, 6, 6, 6)
        frame_layout.setSpacing(4)

        # Avatar label
        self.label = QLabel()
        self.label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.label.setStyleSheet("background: transparent;")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame_layout.addWidget(self.label, stretch=1)

        # Control bar
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setContentsMargins(2, 0, 2, 2)
        ctrl_layout.setSpacing(4)

        # Character name label
        self.char_label = QLabel()
        self.char_label.setStyleSheet("color: rgba(180, 200, 255, 0.6); font-size: 9px; font-weight: bold; padding: 0 4px;")
        self.char_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        ctrl_layout.addWidget(self.char_label, stretch=1)

        # Prev character button
        self.prev_btn = QPushButton("◀")
        self.prev_btn.setStyleSheet(BTN_STYLE)
        self.prev_btn.setToolTip("Previous character")
        self.prev_btn.clicked.connect(self._prev_character)
        ctrl_layout.addWidget(self.prev_btn)

        # Next character button
        self.next_btn = QPushButton("▶")
        self.next_btn.setStyleSheet(BTN_STYLE)
        self.next_btn.setToolTip("Next character")
        self.next_btn.clicked.connect(self._next_character)
        ctrl_layout.addWidget(self.next_btn)

        # Settings gear button
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setStyleSheet(BTN_STYLE)
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.clicked.connect(self._show_settings)
        ctrl_layout.addWidget(self.settings_btn)

        frame_layout.addLayout(ctrl_layout)

        # Calculate total size
        total_size = self._avatar_size + FRAME_PADDING
        self.resize(total_size, total_size)
        self.frame_widget.resize(total_size, total_size)

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

        # Settings popup
        self._settings_popup: SettingsPopup | None = None

        self.set_character(default_character)
        self._anchor_bottom_right()
        self.setMouseTracking(True)

    # -- positioning ---------------------------------------------------------

    def _anchor_bottom_right(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.x() + geo.width() - self.width() - MARGIN
        y = geo.y() + geo.height() - self.height() - MARGIN - 40  # offset for taskbar
        self.move(x, y)

    # -- character navigation ------------------------------------------------

    def _prev_character(self) -> None:
        if not self.character_list or not self.character:
            return
        idx = self.character_list.index(self.character)
        idx = (idx - 1) % len(self.character_list)
        self.set_character(self.character_list[idx])

    def _next_character(self) -> None:
        if not self.character_list or not self.character:
            return
        idx = self.character_list.index(self.character)
        idx = (idx + 1) % len(self.character_list)
        self.set_character(self.character_list[idx])

    def _show_settings(self) -> None:
        if self._settings_popup and self._settings_popup.isVisible():
            self._settings_popup.close()
            return
        button_pos = self.settings_btn.mapToGlobal(self.settings_btn.rect().topLeft())
        self._settings_popup = SettingsPopup(self, self.character_list, self.character)
        self._settings_popup.show_at(button_pos.x(), button_pos.y())

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
                continue
            loaded[viseme] = pix.scaled(
                self._avatar_size,
                self._avatar_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        if not loaded:
            return
        self.character = name
        self.frames = loaded
        # Update name label
        display = name.replace("-", " ").title()
        self.char_label.setText(display)
        self._show_viseme("X")
        # Update settings popup combo if open
        if self._settings_popup and self._settings_popup.isVisible():
            self._settings_popup.combo.blockSignals(True)
            self._settings_popup.combo.setCurrentText(name)
            self._settings_popup.combo.blockSignals(False)

    def resize_avatar(self, size: int) -> None:
        self._avatar_size = size
        # Reload frames at new size
        self.frames = {}
        self.set_character(self.character)
        # Resize window
        total = size + FRAME_PADDING
        self.resize(total, total)
        self.frame_widget.resize(total, total)
        self._anchor_bottom_right()

    # -- viseme rendering ----------------------------------------------------

    def _show_viseme(self, viseme: str) -> None:
        pix = self.frames.get(viseme) or self.frames.get("X")
        if pix is None:
            return
        canvas = QPixmap(self.label.size())
        canvas.fill(Qt.GlobalColor.transparent)
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
        self._show_viseme("X")

    def _idle_blink_tick(self) -> None:
        if self._playing:
            return
        self._show_viseme("A")
        QTimer.singleShot(120, lambda: self._show_viseme("X") if not self._playing else None)


# ── Command router ───────────────────────────────────────────────────

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


# ── Entry point ──────────────────────────────────────────────────────

def _load_manifest(base: Path) -> dict:
    return yaml.safe_load((base / "characters.yaml").read_text())


def _demo_cues(duration: float = 3.5) -> list[dict]:
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
