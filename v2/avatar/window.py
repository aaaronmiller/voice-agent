"""Floating avatar window — runs as its own process to keep the Qt event loop
clear of the assistant's audio/STT loops.

Protocol (line-delimited JSON on stdin, one object per line):

    {"cmd":"set_character", "name":"raccoon-hacker"}
    {"cmd":"set_frame_style", "shape":"rounded", "hue":220, "saturation":80,
     "lightness":50, "opacity":0.55, "border_width":1.5, "glow_intensity":40,
     "pulse_speed":0.0, "pulse_amplitude":20}
    {"cmd":"set_volume", "value":0.8}
    {"cmd":"play", "cues":[...], "duration":2.6}
    {"cmd":"stop"}
    {"cmd":"quit"}

Settings changes are echoed back on stdout as JSON so the controller can
forward them to the assistant.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from PyQt6.QtCore import QObject, QPointF, QSizeF, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QAction, QColor, QCursor, QFont, QGuiApplication, QIcon, QPainter,
    QPainterPath, QPen, QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsBlurEffect,
    QGraphicsDropShadowEffect,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QFormLayout,
    QMenu,
    QSpinBox,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .settings_popup import SettingsPopup  # noqa: E402


VISEMES: tuple[str, ...] = ("X", "A", "B", "C", "D", "E", "F", "G", "H")
DEFAULT_SIZE = 220
MARGIN = 16
IDLE_BLINK_PERIOD_S = 4.5

# Named pipe for external IPC (e.g., hotkey toggle outside the assistant)
AVATAR_FIFO = "/tmp/echo-node-avatar.fifo"

# ── Default frame style (HSL) ───────────────────────────────────────

SHAPES = ["square", "rounded", "circle"]
DEFAULT_SHAPE = "rounded"
DEFAULT_HUE = 220
DEFAULT_SATURATION = 80
DEFAULT_LIGHTNESS = 55
DEFAULT_OPACITY = 0.55
DEFAULT_BORDER_WIDTH = 1.5
DEFAULT_GLOW_INTENSITY = 35      # 0-100, maps to blur radius 0-60px
DEFAULT_PULSE_SPEED = 0.0        # 0 = off, 0.1-5.0 = period in seconds
DEFAULT_PULSE_AMPLITUDE = 20     # how much the glow varies (0-100)

# Quick-pick HSL presets for the colour swatches
QUICK_COLORS: list[dict[str, Any]] = [
    {"label": "Blue",   "hue": 220, "sat": 80,  "lig": 55},
    {"label": "Green",  "hue": 140, "sat": 75,  "lig": 50},
    {"label": "Purple", "hue": 280, "sat": 70,  "lig": 55},
    {"label": "Amber",  "hue": 40,  "sat": 90,  "lig": 55},
    {"label": "Red",    "hue": 0,   "sat": 85,  "lig": 50},
    {"label": "Cyan",   "hue": 190, "sat": 85,  "lig": 50},
    {"label": "Pink",   "hue": 330, "sat": 80,  "lig": 55},
    {"label": "Mint",   "hue": 160, "sat": 65,  "lig": 45},
    {"label": "White",  "hue": 220, "sat": 15,  "lig": 85},
    {"label": "Lava",   "hue": 15,  "sat": 90,  "lig": 45},
]

BTN_STYLE = """
    QPushButton {
        background: rgba(60,60,90,0.70);
        color: #ccd;
        border: 1px solid rgba(100,180,255,0.30);
        border-radius: 10px;
        padding: 2px 6px;
        font-size: 11px;
        font-weight: bold;
        min-width: 22px;
        min-height: 22px;
    }
    QPushButton:hover {
        background: rgba(100,180,255,0.40);
        border: 1px solid rgba(150,200,255,0.6);
    }
    QPushButton:checked {
        background: rgba(100,180,255,0.35);
        border: 1.5px solid rgba(100,180,255,0.7);
    }
"""

POPUP_STYLE = """
    QFrame#settingsFrame {
        background: #1a1a2e;
        border: 1px solid rgba(100,160,255,0.25);
        border-radius: 16px;
    }
    QLabel {
        color: #bcc;
        font-size: 9px;
        font-weight: bold;
        letter-spacing: 0.5px;
        text-transform: uppercase;
    }
    QLabel#title {
        font-size: 13px;
        color: #eef;
        text-transform: none;
        letter-spacing: 0;
    }
    QLabel#value {
        font-size: 9px;
        color: #889;
        min-width: 28px;
    }
    QComboBox {
        background: rgba(40,40,70,0.80);
        color: #dde;
        border: 1px solid rgba(100,180,255,0.20);
        border-radius: 6px;
        padding: 3px 8px;
        font-size: 10px;
        min-width: 80px;
    }
    QComboBox::drop-down { border: none; }
    QComboBox QAbstractItemView {
        background: rgba(20,20,45,0.96);
        color: #dde;
        selection-background-color: rgba(100,180,255,0.25);
        border: 1px solid rgba(100,180,255,0.15);
        border-radius: 4px;
        outline: none;
    }
    QSlider::groove:horizontal {
        height: 2px;
        background: rgba(60,60,100,0.4);
        border-radius: 1px;
    }
    QSlider::handle:horizontal {
        background: rgba(100,180,255,0.80);
        width: 8px;
        height: 8px;
        margin: -3px 0;
        border-radius: 4px;
    }
    QSlider::sub-page:horizontal {
        background: rgba(100,180,255,0.25);
        border-radius: 1px;
    }
    QSlider::handle:horizontal:hover {
        background: rgba(140,210,255,0.95);
        width: 10px;
        height: 10px;
        margin: -4px 0;
        border-radius: 5px;
    }
"""


# ── HSL colour helpers ──────────────────────────────────────────────

def hsl_css(hue: int, sat: int, lig: int, alpha: float) -> str:
    """Returns an `hsla(h, s%, l%, a)` CSS string."""
    return f"hsla({hue},{sat}%,{lig}%,{alpha})"


def hsl_to_qcolor(hue: int, sat: int, lig: int) -> QColor:
    c = QColor()
    c.setHsl(hue % 360, max(0, min(255, sat * 255 // 100)),
             max(0, min(255, lig * 255 // 100)))
    return c


# ── Stdin reader thread ─────────────────────────────────────────────

class StdinReader(QThread):
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


# ── Quick-colour swatch button ──────────────────────────────────────

class QuickColorButton(QPushButton):
    """A tiny round button that shows a preview of a HSL preset."""

    def __init__(self, preset: dict[str, Any], parent: QWidget | None = None):
        super().__init__(parent)
        self.preset = preset
        self.setCheckable(True)
        self.setFixedSize(20, 20)
        bg = hsl_css(preset["hue"], preset["sat"], preset["lig"], alpha=0.80)
        border = hsl_css(preset["hue"], preset["sat"], min(100, preset["lig"] + 30), alpha=0.5)
        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                border: 1.5px solid {border};
                border-radius: 10px;
            }}
            QPushButton:hover {{
                border: 1.5px solid white;
            }}
            QPushButton:checked {{
                border: 2.5px solid white;
                background: {hsl_css(preset["hue"], preset["sat"], preset["lig"], alpha=1.0)};
            }}
        """)
        self.setToolTip(f"{preset['label']} (H:{preset['hue']} S:{preset['sat']}% L:{preset['lig']}%)")


# ── Debug overlay widget ───────────────────────────────────────────

class _DebugPanel(QWidget):
    """Dedicated debug panel that sits below the avatar in the frame layout.

    Layout (full width of the avatar frame):
      ┌──────────────────────────────────┐
      │ VAD ▓▓▓ T0.40 B0.54  │  RMS ▓▓▓ R500 BR800  │  PLAYING │
      │ ≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈ │
      │   scrolling waveform (color-coded)           │
      └──────────────────────────────────┘

    Toggled via:  {"cmd":"debug_overlay", "enabled":true}
    Updated via:  {"cmd":"debug_update", "vad":0.45, "rms":600, ...}
    """

    # Colour palette for waveform points
    _GREEN = QColor(60, 220, 100)
    _YELLOW = QColor(240, 210, 60)
    _RED = QColor(240, 80, 60)
    _DIM_GREEN = QColor(60, 220, 100, 100)
    _DIM_YELLOW = QColor(240, 210, 60, 100)
    _DIM_RED = QColor(240, 80, 60, 100)
    _GREEN_LIGHT = QColor(60, 220, 100, 180)
    _YELLOW_LIGHT = QColor(240, 210, 60, 180)
    _RED_LIGHT = QColor(240, 80, 60, 180)

    def __init__(self, data_ref: dict[str, float],
                 history_ref: list[float]):
        super().__init__()
        self._data = data_ref
        self._history = history_ref
        self._max_history = 160
        self.setFixedHeight(64)
        self.setMinimumWidth(80)
        # Solid background — always visible
        self.setStyleSheet("""
            _DebugPanel {
                background: rgba(10, 12, 28, 0.92);
                border: 1px solid rgba(80, 120, 200, 0.25);
                border-radius: 6px;
            }
        """)

    def paintEvent(self, event):
        if not self._data:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w = self.width()
        h = self.height()
        if w < 20 or h < 20:
            painter.end()
            return

        # Background
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(10, 12, 28, 235))
        painter.drawRoundedRect(0, 0, w, h, 6, 6)
        # Border
        painter.setPen(QPen(QColor(80, 120, 200, 60), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(1, 1, w - 2, h - 2, 5, 5)

        d = self._data
        vad = d.get("vad", 0.0)
        rms = d.get("rms", 0.0)
        threshold = d.get("threshold", 0.40)
        boosted = d.get("boosted_threshold", 0.54)
        rms_floor = d.get("rms_floor", 500)
        boosted_rms = d.get("boosted_rms", 800)
        state = d.get("state", "idle")
        max_rms = max(2000, boosted_rms * 2)

        m = 2          # margin
        info_h = 14    # height of stats bar at top
        bar_h = h - m * 2 - 2
        wave_h = bar_h - info_h - 2  # waveform fills everything below stats
        wave_y = m + info_h + 2
        wave_x = m
        wave_w = w - m * 2

        font_tiny = QFont("monospace", 7)
        font_bold = QFont("monospace", 7)
        font_bold.setBold(True)

        # ── Top stats bar (compact, full-width) ──
        painter.setFont(font_tiny)
        painter.setPen(QColor(140, 170, 220, 200))

        # Stats: VAD score with color, RMS with floor, state
        vad_str = f"VAD {vad:.2f}"
        if vad >= boosted:
            painter.setPen(QPen(self._RED_LIGHT, 1))
        elif vad >= threshold:
            painter.setPen(QPen(self._YELLOW_LIGHT, 1))
        else:
            painter.setPen(QPen(self._GREEN_LIGHT, 1))
        painter.drawText(m + 2, m + info_h - 2, vad_str)

        rms_str = f"RMS {rms:.0f} F{rms_floor:.0f}"
        painter.setPen(QColor(140, 170, 220, 200))
        painter.drawText(m + 70, m + info_h - 2, rms_str)

        painter.setFont(font_bold)
        state_colors = {
            "idle": QColor(80, 160, 255, 160),
            "listening": QColor(60, 220, 120, 200),
            "transcribing": QColor(240, 210, 60, 200),
            "working": QColor(240, 160, 40, 200),
            "responding": QColor(60, 200, 255, 200),
        }
        painter.setPen(state_colors.get(state, QColor(100, 100, 140, 160)))
        painter.drawText(wave_x + wave_w - 60, m + info_h - 2, state.upper())

        # ── Waveform area ──
        if wave_w > 10 and len(self._history) > 1:
            hist = self._history[-self._max_history:]
            n = len(hist)
            if n > 1:
                step_x = wave_w / (n - 1)
                mid_y = wave_y + wave_h / 2

                # Grid lines (subtle)
                painter.setPen(QPen(QColor(60, 80, 140, 20), 1))
                for gx in range(int(wave_x) + 20, int(wave_x + wave_w), 20):
                    painter.drawLine(gx, wave_y, gx, wave_y + wave_h)
                painter.setPen(QPen(QColor(60, 80, 140, 25), 1))
                gy = mid_y
                painter.drawLine(wave_x, gy, wave_x + wave_w, gy)
                for gy in (wave_y + wave_h // 4, wave_y + 3 * wave_h // 4):
                    painter.drawLine(wave_x, gy, wave_x + wave_w, gy)

                # Build polygon points for filled waveform
                points: list[QPointF] = []
                points.append(QPointF(wave_x, mid_y))
                for i in range(n):
                    val = hist[i]
                    norm = min(1.0, val / max_rms)
                    px = wave_x + i * step_x
                    py = mid_y - norm * wave_h / 2  # center-biased
                    points.append(QPointF(px, py))
                points.append(QPointF(wave_x + (n - 1) * step_x, mid_y))

                # Fill under waveform (gradient-like)
                poly_color = QColor(80, 140, 255, 30)
                painter.setBrush(poly_color)
                painter.setPen(Qt.PenStyle.NoPen)
                for i in range(1, n):
                    val = hist[i]
                    norm = min(1.0, val / max_rms)
                    px1 = wave_x + (i - 1) * step_x
                    px2 = wave_x + i * step_x
                    py1 = mid_y - min(1.0, hist[i - 1] / max_rms) * wave_h / 2
                    py2 = mid_y - norm * wave_h / 2
                    fill_col = QColor(80, 140, 255, max(5, int(25 * norm)))
                    painter.setBrush(fill_col)
                    painter.drawRect(int(px1), int(py2), max(1, int(px2 - px1)), int(mid_y - py2))

                # Draw waveform line segments (color-coded by amplitude)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                for i in range(1, n):
                    val_prev = hist[i - 1]
                    val_cur = hist[i]
                    norm_prev = min(1.0, val_prev / max_rms)
                    norm_cur = min(1.0, val_cur / max_rms)

                    px1 = wave_x + (i - 1) * step_x
                    px2 = wave_x + i * step_x
                    py1 = mid_y - norm_prev * wave_h / 2
                    py2 = mid_y - norm_cur * wave_h / 2

                    avg = (norm_prev + norm_cur) / 2
                    if avg > 0.80:
                        color = self._RED
                    elif avg > 0.50:
                        color = self._YELLOW
                    else:
                        color = self._GREEN

                    # Thicker line for higher amplitudes
                    line_w = 1.0 + avg * 2.0
                    painter.setPen(QPen(color, line_w))
                    painter.drawLine(px1, py1, px2, py2)

        painter.end()


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
        self.setMouseTracking(True)

        self.frames_root = frames_root
        self.manifest = manifest
        self.character_list = list(manifest.get("characters", {}).keys())
        self.character: str = ""
        self.frames: dict[str, QPixmap] = {}
        self._avatar_size = DEFAULT_SIZE
        self._min_size = 100
        self._max_size = 600

        # Drag state
        self._drag_pos: QPointF | None = None
        # Resize state
        self._resizing = False
        self._resize_edge = 0  # bitmask: 1=left, 2=right, 4=top, 8=bottom
        self._resize_start_pos: QPointF | None = None
        self._resize_start_size: QSizeF | None = None
        self.RESIZE_MARGIN = 8  # px from edge to detect resize

        # ── Assistant state for visual indicators ──
        self._assistant_state: str = "idle"

        # ── Frame style state (HSL) ──
        self._frame_shape = DEFAULT_SHAPE
        self._hue = DEFAULT_HUE
        self._saturation = DEFAULT_SATURATION
        self._lightness = DEFAULT_LIGHTNESS
        self._frame_opacity = DEFAULT_OPACITY
        self._frame_border_width = DEFAULT_BORDER_WIDTH
        self._glow_intensity = DEFAULT_GLOW_INTENSITY
        self._pulse_speed = DEFAULT_PULSE_SPEED          # 0 = off, >0 = period s
        self._pulse_amplitude = DEFAULT_PULSE_AMPLITUDE  # 0-100

        # ── Blink ──
        self._blink_interval = IDLE_BLINK_PERIOD_S

        # Root styling
        self.setStyleSheet("background: transparent;")

        # ── Glow effect (drop shadow) ──
        self._glow_effect = QGraphicsDropShadowEffect(self)
        self._glow_effect.setBlurRadius(30)
        self._glow_effect.setOffset(0, 0)
        self._glow_effect.setColor(self._get_glow_color())

        # Outer frame widget — install event filter to forward mouse events
        # to AvatarWindow for drag/resize (label is already transparent, but
        # QFrame would otherwise eat the event)
        self.frame_widget = QFrame(self)
        self.frame_widget.setGraphicsEffect(self._glow_effect)
        self.frame_widget.installEventFilter(self)
        self._apply_frame_style()

        # Layout inside frame
        frame_layout = QVBoxLayout(self.frame_widget)
        frame_layout.setContentsMargins(8, 4, 8, 8)
        frame_layout.setSpacing(4)

        # ── Title bar (drag handle + close) ──
        title_bar = QHBoxLayout()
        title_bar.setContentsMargins(4, 0, 0, 0)
        title_bar.setSpacing(2)

        self._title_label = QLabel()
        self._title_label.setStyleSheet("color: rgba(180,200,255,0.35); font-size: 8px; padding: 0;")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        title_bar.addWidget(self._title_label, stretch=1)

        self._min_btn = QPushButton("─")
        self._min_btn.setFixedSize(16, 16)
        self._min_btn.setStyleSheet("""
            QPushButton { background: rgba(60,60,90,0.50); color: #889; border: none; border-radius: 8px; font-size: 8px; }
            QPushButton:hover { background: rgba(100,140,200,0.40); color: #dde; }
        """)
        self._min_btn.setToolTip("Minimize to tray")
        self._min_btn.clicked.connect(self._minimize_to_tray)
        title_bar.addWidget(self._min_btn)

        self._close_btn = QPushButton("✕")
        self._close_btn.setFixedSize(16, 16)
        self._close_btn.setStyleSheet("""
            QPushButton { background: rgba(200,60,60,0.40); color: #c88; border: none; border-radius: 8px; font-size: 8px; }
            QPushButton:hover { background: rgba(220,80,80,0.70); color: white; }
        """)
        self._close_btn.setToolTip("Close to tray")
        self._close_btn.clicked.connect(self._minimize_to_tray)
        title_bar.addWidget(self._close_btn)

        frame_layout.addLayout(title_bar)

        # Avatar sprite — transparent for mouse events so clicks pass through
        # to AvatarWindow for dragging (the frameless window relies on manual drag)
        self.label = QLabel()
        self.label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.label.setStyleSheet("background: transparent;")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame_layout.addWidget(self.label, stretch=1)

        # Track last visible viseme for live-resize re-render
        self._current_viseme: str = "X"

        # ── Tray icon state ──
        self._tray_glyph: str = NERD_ICON_PRESETS[0][0]
        self._tray_state_ref: dict[str, Any] | None = None
        self._tray_state_action: QAction | None = None

        # ── Debug panel (hidden by default, toggled via IPC) ──
        self._debug_data: dict[str, float] = {
            "vad": 0.0, "rms": 0.0, "threshold": 0.40,
            "boosted_threshold": 0.54, "rms_floor": 500,
            "boosted_rms": 800, "state": "idle",
        }
        self._debug_history: list[float] = []
        self._debug_panel = _DebugPanel(self._debug_data, self._debug_history)
        self._debug_panel.hide()
        frame_layout.addWidget(self._debug_panel)

        # Auto-show debug waveform on startup
        self._debug_enabled = True
        self._debug_panel.show()
        # ── Debug panel refresh timer (10 fps when visible) ──
        self._debug_timer = QTimer(self)
        self._debug_timer.setInterval(100)
        self._debug_timer.timeout.connect(self._debug_repaint)
        self._debug_timer.start()

        # ── Control bar ──
        ctrl = QHBoxLayout()
        ctrl.setContentsMargins(2, 0, 2, 2)
        ctrl.setSpacing(3)

        self.char_label = QLabel()
        self.char_label.setStyleSheet("color: rgba(180,200,255,0.50); font-size: 9px; font-weight: bold; padding: 0 2px;")
        self.char_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        ctrl.addWidget(self.char_label, stretch=1)

        self.prev_btn = QPushButton("◀")
        self.prev_btn.setStyleSheet(BTN_STYLE)
        self.prev_btn.setToolTip("Previous character")
        self.prev_btn.clicked.connect(self._prev_character)
        ctrl.addWidget(self.prev_btn)

        self.next_btn = QPushButton("▶")
        self.next_btn.setStyleSheet(BTN_STYLE)
        self.next_btn.setToolTip("Next character")
        self.next_btn.clicked.connect(self._next_character)
        ctrl.addWidget(self.next_btn)

        self.settings_btn = QPushButton("✦")
        self.settings_btn.setStyleSheet(BTN_STYLE)
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.clicked.connect(self._toggle_settings)
        ctrl.addWidget(self.settings_btn)

        frame_layout.addLayout(ctrl)

        self._update_window_size()

        # Playback state
        self._cues: list[dict] = []
        self._play_start_monotonic: float = 0.0
        self._duration: float = 0.0
        self._cue_index: int = 0
        self._playing: bool = False

        self._tick = QTimer(self)
        self._tick.setInterval(16)
        self._tick.timeout.connect(self._on_tick)

        self._idle_blink = QTimer(self)
        self._idle_blink.timeout.connect(self._idle_blink_tick)
        self._restart_idle_blink()

        # ── Pulse animation ──
        self._pulse_tick = 0.0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(33)  # ~30 fps
        self._pulse_timer.timeout.connect(self._on_pulse_tick)

        # Settings popup
        self._settings_popup: SettingsPopup | None = None

        self.set_character(default_character)
        self._anchor_bottom_right()

    # ── HSL colour generation ────────────────────────────────────────────

    def _get_bg_color(self) -> str:
        """Frame background: low luminance, full alpha from opacity."""
        bg_lig = max(3, min(20, self._lightness // 3))
        return hsl_css(self._hue, max(20, self._saturation), bg_lig, self._frame_opacity)

    def _get_border_color(self) -> str:
        """Frame border: bright with moderate alpha.
        Overrides to bright green when listening, cyan when responding."""
        if self._assistant_state == "listening":
            return "rgba(60, 255, 120, 0.8)"
        if self._assistant_state == "transcribing":
            return "rgba(240, 210, 60, 0.8)"
        if self._assistant_state == "working":
            return "rgba(240, 160, 40, 0.8)"
        if self._assistant_state == "responding":
            return "rgba(60, 200, 255, 0.8)"
        b_lig = min(100, self._lightness + 25)
        b_alpha = max(0.15, 0.25 + (self._lightness / 200))
        return hsl_css(self._hue, self._saturation, b_lig, b_alpha)

    def _get_glow_color(self) -> QColor:
        """The glow shadow colour (QColor, not CSS).
        Overrides to bright state colors when assistant is active."""
        c = QColor()
        intensity = max(0.01, self._glow_intensity / 100)
        alpha = max(0, min(255, int(180 * intensity)))
        if self._assistant_state == "listening":
            c.setHsl(130, 255, 140, alpha)
            return c
        if self._assistant_state == "transcribing":
            c.setHsl(50, 230, 150, alpha)
            return c
        if self._assistant_state == "working":
            c.setHsl(35, 230, 150, alpha)
            return c
        if self._assistant_state == "responding":
            c.setHsl(200, 230, 150, alpha)
            return c
        glow_lig = min(100, self._lightness + 10)
        c.setHsl(self._hue % 360,
                 max(0, min(255, self._saturation * 255 // 100)),
                 max(0, min(255, glow_lig * 255 // 100)),
                 alpha)
        return c

    def _get_glow_blur(self) -> int:
        """Map glow_intensity to blur radius: 5-60px."""
        # Bigger glow when active
        if self._assistant_state != "idle":
            return max(20, int(self._glow_intensity * 0.8))
        return max(5, int(self._glow_intensity * 0.6))

    # ── Frame CSS generation ─────────────────────────────────────────────

    def _make_frame_css(self) -> str:
        r = 0
        if self._frame_shape == "rounded":
            r = 18
        elif self._frame_shape == "circle":
            r = 999
        bw = max(0.5, self._frame_border_width)
        return f"""
            QFrame {{
                background: {self._get_bg_color()};
                border: {bw}px solid {self._get_border_color()};
                border-radius: {r}px;
            }}
        """

    def _apply_frame_style(self) -> None:
        self.frame_widget.setStyleSheet(self._make_frame_css())
        self._glow_effect.setColor(self._get_glow_color())
        self._glow_effect.setBlurRadius(self._get_glow_blur())

    # ── Pulse animation ──────────────────────────────────────────────────

    def _start_pulse(self) -> None:
        self._pulse_tick = 0.0
        if self._pulse_speed > 0 and self._glow_intensity > 0:
            self._pulse_timer.start()

    def _stop_pulse(self) -> None:
        self._pulse_timer.stop()
        self._pulse_tick = 0.0
        self._glow_effect.setColor(self._get_glow_color())
        self._glow_effect.setBlurRadius(self._get_glow_blur())

    # ── Debug panel ────────────────────────────────────────────────────

    def _debug_repaint(self) -> None:
        """Called by _debug_timer to refresh the debug panel."""
        if self._debug_enabled and self._debug_panel:
            self._debug_panel.update()

    def set_debug_enabled(self, enabled: bool) -> None:
        self._debug_enabled = enabled
        self._debug_panel.setVisible(enabled)
        if enabled:
            self._debug_timer.start()
        else:
            self._debug_timer.stop()

    def update_debug_data(self, **kw: float) -> None:
        """Update VAD/RMS/threshold values from the assistant."""
        self._debug_data.update(kw)
        # Track RMS history for scrolling waveform
        if "rms" in kw:
            self._debug_history.append(kw["rms"])
            if len(self._debug_history) > 200:
                self._debug_history[:] = self._debug_history[-200:]
        # Update tray icon state when assistant state changes
        state = kw.get("state")
        if state:
            self._assistant_state = state
            self._apply_frame_style()
        if state and state in _STATE_COLORS and self._tray_state_ref:
            _update_tray_icon(self._tray_state_ref, state=state)

    def _on_pulse_tick(self) -> None:
        if self._pulse_speed <= 0 or self._glow_intensity <= 0:
            self._stop_pulse()
            return
        self._pulse_tick += 0.033
        period = self._pulse_speed
        amplitude = self._pulse_amplitude / 100  # 0-1
        phase = math.sin(self._pulse_tick * (2 * math.pi / period))
        # Modulate alpha and blur radius
        base_alpha = max(0.01, self._glow_intensity / 100)
        modulated = base_alpha * (1.0 + amplitude * phase * 0.6)
        modulated = max(0.01, min(1.0, modulated))

        c = QColor()
        glow_lig = min(100, self._lightness + 10)
        c.setHsl(self._hue % 360,
                 max(0, min(255, self._saturation * 255 // 100)),
                 max(0, min(255, glow_lig * 255 // 100)),
                 max(0, min(255, int(200 * modulated))))
        self._glow_effect.setColor(c)

        # Slightly wobble blur radius too
        base_blur = self._get_glow_blur()
        wobble = base_blur * (1.0 + amplitude * phase * 0.15)
        self._glow_effect.setBlurRadius(max(5, int(wobble)))

    # ── Frame style commands ─────────────────────────────────────────────

    def set_frame_style(self, **kw: Any) -> None:
        changed = False
        for k in ("shape", "hue", "saturation", "lightness", "opacity",
                  "border_width", "glow_intensity", "pulse_speed", "pulse_amplitude"):
            if k in kw:
                v = kw[k]
                attr = f"_frame_{k}" if k in ("shape",) else f"_{k}"
                v = float(v) if k in ("opacity", "border_width", "pulse_speed", "pulse_amplitude") else int(v)
                if k == "shape":
                    if v in SHAPES:
                        setattr(self, attr, v)
                        changed = True
                elif k == "opacity":
                    self._frame_opacity = max(0.05, min(1.0, v))
                    changed = True
                elif k == "border_width":
                    self._frame_border_width = max(0, min(10, v))
                    changed = True
                elif k == "pulse_speed":
                    self._pulse_speed = max(0, min(10, v))
                    changed = True
                elif k == "pulse_amplitude":
                    self._pulse_amplitude = max(0, min(100, int(v)))
                    changed = True
                else:
                    # hue, saturation, lightness, glow_intensity
                    val = int(max(0, min(100, v)))
                    if k == "hue":
                        val = v % 360
                    setattr(self, f"_{k}", val)
                    changed = True
        if changed:
            self._apply_frame_style()
            if self._pulse_speed > 0 and self._glow_intensity > 0:
                self._start_pulse()
            else:
                self._stop_pulse()

    def _frame_state_dict(self) -> dict[str, Any]:
        return {
            "shape": self._frame_shape,
            "hue": self._hue,
            "saturation": self._saturation,
            "lightness": self._lightness,
            "opacity": self._frame_opacity,
            "border_width": self._frame_border_width,
            "glow_intensity": self._glow_intensity,
            "pulse_speed": self._pulse_speed,
            "pulse_amplitude": self._pulse_amplitude,
        }

    # ── Window sizing ────────────────────────────────────────────────────

    def _update_window_size(self) -> None:
        total = self._avatar_size + 56
        self.resize(total, total)
        self.frame_widget.resize(total, total)

    def _anchor_bottom_right(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.x() + geo.width() - self.width() - MARGIN
        y = geo.y() + geo.height() - self.height() - MARGIN - 40
        self.move(x, y)

    # ── Window chrome: drag, resize, minimize ────────────────────────────

    def _minimize_to_tray(self) -> None:
        self.hide()

    def eventFilter(self, obj: QObject, event) -> bool:
        """Forward mouse events from child widgets to AvatarWindow handlers.

        The frameless window relies on manual drag/resize in mousePress/Move/Release,
        but child widgets (QFrame, QLabel) would otherwise consume those events.
        Labels are set WA_TransparentForMouseEvents; the QFrame needs forwarding.
        """
        if obj is self.frame_widget:
            if event.type() == event.Type.MouseButtonPress:
                self.mousePressEvent(event)
                return True
            elif event.type() == event.Type.MouseMove:
                self.mouseMoveEvent(event)
                return True
            elif event.type() == event.Type.MouseButtonRelease:
                self.mouseReleaseEvent(event)
                return True
        return super().eventFilter(obj, event)

    def _edge_at(self, pos: QPointF) -> int:
        """Return bitmask of edges at the given local position."""
        m = self.RESIZE_MARGIN
        w, h = self.width(), self.height()
        edges = 0
        if pos.x() < m:
            edges |= 1  # left
        if pos.x() > w - m:
            edges |= 2  # right
        if pos.y() < m:
            edges |= 4  # top
        if pos.y() > h - m:
            edges |= 8  # bottom
        return edges

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            edge = self._edge_at(event.position())
            if edge:
                self._resizing = True
                self._resize_edge = edge
                self._resize_start_pos = event.position()
                self._resize_start_size = QSizeF(self.size())
            else:
                self._drag_pos = event.position()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = None
            self._resizing = False
            self._resize_edge = 0
            self._resize_start_pos = None
            self._resize_start_size = None
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._resizing and self._resize_start_pos and self._resize_start_size:
            dx = pos.x() - self._resize_start_pos.x()
            dy = pos.y() - self._resize_start_pos.y()
            edge = self._resize_edge
            new_w = self._resize_start_size.width()
            new_h = self._resize_start_size.height()
            new_x = self.x()
            new_y = self.y()

            if edge & 1:  # left
                new_w -= dx
                new_x += dx
            if edge & 2:  # right
                new_w += dx
            if edge & 4:  # top
                new_h -= dy
                new_y += dy
            if edge & 8:  # bottom
                new_h += dy

            new_w = max(self._min_size, int(new_w))
            new_h = max(self._min_size, int(new_h))
            av_size = min(new_w, new_h) - 56
            if av_size >= self._min_size:
                self._avatar_size = av_size
                # Re-scale existing frames (fast) instead of reloading from disk
                if self.frames:
                    self._scale_frames()
                self.frame_widget.resize(new_w, new_h)
            self.resize(new_w, new_h)
            if edge & (1 | 4):
                self.move(new_x, new_y)
        elif self._drag_pos is not None:
            self.move(self.pos() + event.position().toPoint() - self._drag_pos.toPoint())
        else:
            edge = self._edge_at(pos)
            cursor = Qt.CursorShape.ArrowCursor
            if edge & 5 == 5 or edge & 10 == 10:  # diagonal: tl or br
                cursor = Qt.CursorShape.SizeFDiagCursor
            elif edge & 6 == 6 or edge & 9 == 9:  # diagonal: bl or tr
                cursor = Qt.CursorShape.SizeBDiagCursor
            elif edge & 3:  # horizontal: l or r
                cursor = Qt.CursorShape.SizeHorCursor
            elif edge & 12:  # vertical: t or b
                cursor = Qt.CursorShape.SizeVerCursor
            self.setCursor(QCursor(cursor))

    # ── Character navigation ─────────────────────────────────────────────

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

    # ── Settings popup ───────────────────────────────────────────────────

    def _toggle_settings(self) -> None:
        if self._settings_popup and self._settings_popup.isVisible():
            self._settings_popup.close()
            return
        btn_pos = self.settings_btn.mapToGlobal(self.settings_btn.rect().topLeft())
        self._settings_popup = SettingsPopup(
            self, self.character_list, self.character, self._frame_state_dict()
        )
        self._settings_popup.setting_changed.connect(self._on_setting_change)
        self._settings_popup.show_at(btn_pos.x(), btn_pos.y())

    def _on_setting_change(self, payload: dict) -> None:
        cmd = payload.get("cmd")
        if cmd == "set_character":
            self.set_character(payload.get("name", ""))
        elif cmd == "set_frame_style":
            self.set_frame_style(**{k: v for k, v in payload.items() if k != "cmd"})
        elif cmd == "set_size":
            self.resize_avatar(int(payload.get("value", DEFAULT_SIZE)))
        elif cmd == "set_blink_interval":
            self._blink_interval = float(payload.get("value", IDLE_BLINK_PERIOD_S))
            self._restart_idle_blink()
        elif cmd == "set_backend":
            # Forward to the assistant via stdout (controller reads it)
            print(json.dumps(payload), flush=True)

    def _restart_idle_blink(self) -> None:
        self._idle_blink.stop()
        if self._blink_interval > 0:
            self._idle_blink.setInterval(int(self._blink_interval * 1000))
            self._idle_blink.start()

    def _set_tray_glyph(self, glyph: str, _name: str = "") -> None:
        """Change the tray icon glyph (called from icon submenu)."""
        self._tray_glyph = glyph
        if self._tray_state_ref:
            _update_tray_icon(self._tray_state_ref, glyph=glyph)
            # Update check marks in tray icon submenu
            for a in self._tray_state_ref.get("icon_group", []):
                a.setChecked(False)
            # Find and check the matching action
            for a in self._tray_state_ref.get("icon_group", []):
                if glyph == getattr(a, "_glyph", None):
                    a.setChecked(True)
                    break

    # ── Character loading ────────────────────────────────────────────────

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
                continue
            pix = QPixmap(str(path))
            if pix.isNull():
                continue
            loaded[viseme] = pix.scaled(
                self._avatar_size, self._avatar_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        if not loaded:
            return
        self.character = name
        self.frames = loaded
        display = name.replace("-", " ").title()
        self.char_label.setText(display)
        self._show_viseme("X")
        if self._settings_popup and self._settings_popup.isVisible():
            self._settings_popup.combo.blockSignals(True)
            self._settings_popup.combo.setCurrentText(name)
            self._settings_popup.combo.blockSignals(False)

    def resize_avatar(self, size: int) -> None:
        self._avatar_size = size
        if self.character in self.character_list and self.frames:
            self._scale_frames()
        else:
            self.frames = {}
            self.set_character(self.character)
        self._update_window_size()
        self._anchor_bottom_right()

    def _scale_frames(self) -> None:
        """Re-scale existing frame pixmaps to the current _avatar_size.
        Called during live resize so we don't reload from disk."""
        if not self.frames:
            return
        scaled: dict[str, QPixmap] = {}
        for viseme, pix in self.frames.items():
            scaled[viseme] = pix.scaled(
                self._avatar_size, self._avatar_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        self.frames = scaled
        self._show_viseme(self._current_viseme or "X")

    # ── Viseme rendering ─────────────────────────────────────────────────

    def _show_viseme(self, viseme: str) -> None:
        self._current_viseme = viseme
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

    # ── Playback loop ────────────────────────────────────────────────────

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
        self._restart_idle_blink()

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
        elif cmd == "set_frame_style":
            self.window.set_frame_style(**{k: v for k, v in payload.items() if k != "cmd"})
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
            self.window.raise_()
            self.window.activateWindow()
        elif cmd == "hide":
            self.window.hide()
        elif cmd == "toggle":
            if self.window.isVisible():
                self.window.hide()
            else:
                self.window.show()
                self.window.raise_()
                self.window.activateWindow()
        elif cmd == "debug_overlay":
            self.window.set_debug_enabled(bool(payload.get("enabled", False)))
        elif cmd == "debug_update":
            self.window.update_debug_data(**{
                k: v for k, v in payload.items()
                if k in ("vad", "rms", "threshold", "boosted_threshold",
                         "rms_floor", "boosted_rms", "state")
            })
        elif cmd == "quit":
            try:
                os.unlink(AVATAR_FIFO)
            except OSError:
                pass
            QApplication.instance().quit()


# ── Named pipe for external IPC ─────────────────────────────────────

class FifoReader(QThread):
    """Reads JSON commands from a named pipe at ``/tmp/echo-node-avatar.fifo``
    so that external scripts (e.g. the Ctrl+Shift+Q hotkey) can toggle the
    avatar window without going through the assistant's stdin."""
    command = pyqtSignal(dict)

    def run(self) -> None:
        import stat as _stat
        try:
            os.mkfifo(AVATAR_FIFO, 0o644)
        except FileExistsError:
            if not _stat.S_ISFIFO(os.stat(AVATAR_FIFO).st_mode):
                os.unlink(AVATAR_FIFO)
                os.mkfifo(AVATAR_FIFO, 0o644)
        except (PermissionError, OSError):
            return

        while not self.isInterruptionRequested():
            try:
                with open(AVATAR_FIFO, "r") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            payload = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(payload, dict):
                            self.command.emit(payload)
            except (OSError, ValueError):
                break


# ── Nerd Font helpers ───────────────────────────────────────────────

NERD_FONT_GLYPH: str = ""  # single char string, e.g. "\uf130" for mic
NERD_FONT_NAME: str = ""  # cached font family name
NERD_FONT_CHECKED: bool = False

# State → colour map for tray icon
_STATE_COLORS: dict[str, QColor] = {
    "idle":        QColor(80, 160, 255, 180),       # dim blue
    "listening":   QColor(60, 220, 120, 220),        # green
    "transcribing": QColor(240, 210, 60, 220),       # yellow
    "working":     QColor(240, 160, 40, 220),        # orange
    "responding":  QColor(60, 200, 255, 220),        # bright cyan
}

# Default icon options (Nerd Font unicode + description)
NERD_ICON_PRESETS: list[tuple[str, str, str]] = [
    ("\uf130", "Microphone", "U+F130"),
    ("\uf82a", "Voice", "U+F82A"),
    ("\uf5b7", "Robot", "U+F5B7"),
    ("\uf718", "Thought Bubble", "U+F718"),
    ("\ue294", "Chat Bubble", "U+E294"),
    ("\uf809", "Chat Processing", "U+F809"),
    ("\ufd1e", "Listening", "U+FD1E"),
    ("\uf542", "Wave", "U+F542"),
    ("\uf23a", "Rocket", "U+F23A"),
    ("\ue200", "Gear", "U+E200"),
]


def _find_nerd_font() -> str:
    """Return the family name of the first Nerd Font installed, or empty.

    Uses the static QFontDatabase.families() method so we don't need to
    instantiate QFontDatabase (broken in PyQt6 6.11.0 which only exposes
    the copy constructor).
    """
    from PyQt6.QtGui import QFontDatabase
    for fam in QFontDatabase.families():
        low = fam.lower()
        if "nerd" in low and "mono" in low:
            return fam
        if "nerd" in low and "font" in low:
            return fam
    return ""


def _nerd_font_available() -> bool:
    global NERD_FONT_NAME, NERD_FONT_CHECKED
    if not NERD_FONT_CHECKED:
        NERD_FONT_NAME = _find_nerd_font()
        NERD_FONT_CHECKED = True
    return bool(NERD_FONT_NAME)


def _render_tray_pixmap(glyph: str, color: QColor, size: int = 32) -> QPixmap:
    """Render a Nerd Font glyph onto a transparent ``size×size`` pixmap.

    Falls back to a filled circle if no Nerd Font is installed.
    """
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    nf = _nerd_font_available()
    if nf:
        font = QFont(NERD_FONT_NAME, size - 8)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        p.setFont(font)
        p.setPen(QPen(color, 1))
        p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, glyph)
    else:
        # Fallback: draw a filled circle with inner highlight
        col = color.toTuple()[:3]
        inner = QColor(*col, 180)
        p.setBrush(inner)
        p.setPen(QPen(color.lighter(130), 1))
        p.drawEllipse(2, 2, size - 4, size - 4)
        p.setBrush(QColor(255, 255, 255, 40))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(size // 4, size // 4, size // 3, size // 3)
    p.end()
    return pix


def _icon_set(glyph: str) -> QIcon:
    """Build a multi-state QIcon from the single glyph."""
    ico = QIcon()
    for state, color in _STATE_COLORS.items():
        pix = _render_tray_pixmap(glyph, color, 32)
        ico.addPixmap(pix, QIcon.Mode.Normal, QIcon.State.Off if state != "idle" else QIcon.State.On)
    return ico


# ── Nerd Font installer (Qt dialog) ────────────────────────────────

def _install_nerd_font_qt(parent: QWidget) -> None:
    """Download and install JetBrainsMono Nerd Font into ~/.local/share/fonts."""
    from PyQt6.QtWidgets import QMessageBox, QProgressDialog

    mb = QMessageBox(parent)
    mb.setWindowTitle("Install Nerd Font")
    mb.setText("Echo-Node uses Nerd Font icons for the system tray.\n\n"
               "The JetBrainsMono Nerd Font will be downloaded (≈2 MB)\n"
               "and installed to your user font directory.\n\n"
               "Proceed?")
    mb.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
    if mb.exec() != QMessageBox.StandardButton.Ok:
        return

    import io, zipfile, urllib.request
    FONT_URL = "https://github.com/ryanoasis/nerd-fonts/releases/download/v3.3.0/JetBrainsMono.zip"
    FONT_DIR = Path.home() / ".local" / "share" / "fonts"
    FONT_DIR.mkdir(parents=True, exist_ok=True)

    prog = QProgressDialog("Downloading Nerd Font…", "Cancel", 0, 0, parent)
    prog.setWindowTitle("Installing")
    prog.setMinimumDuration(0)
    prog.show()

    try:
        resp = urllib.request.urlopen(FONT_URL, timeout=30)
        data = resp.read()
        if prog.wasCanceled():
            prog.close()
            return

        prog.setLabelText("Extracting…")
        zf = zipfile.ZipFile(io.BytesIO(data))
        installed = 0
        for name in zf.namelist():
            if name.endswith(".ttf") or name.endswith(".otf"):
                zf.extract(name, str(FONT_DIR))
                installed += 1
        zf.close()

        # Rebuild font cache
        import subprocess
        subprocess.run(["fc-cache", "-f", str(FONT_DIR)], capture_output=True, timeout=30)

        # Reset cached check so _nerd_font_available() re-scans
        global NERD_FONT_CHECKED, NERD_FONT_NAME
        NERD_FONT_CHECKED = False
        NERD_FONT_NAME = ""

        prog.close()
        QMessageBox.information(parent, "Done",
                                f"Installed {installed} font files.\n"
                                "Restart Echo-Node to use Nerd Font icons.")
    except Exception as exc:
        prog.close()
        QMessageBox.warning(parent, "Error", f"Font install failed:\n{exc}")


# ── Tray icon builder ───────────────────────────────────────────────

def _make_tray_icon(window: AvatarWindow, router: CommandRouter) -> tuple[QSystemTrayIcon, dict[str, Any]]:
    """Create a system tray icon with context menu.

    Returns (tray, state_ref) where state_ref is a mutable dict the caller can
    use to update the icon dynamically via ``state_ref["glyph"]`` and
    ``state_ref["state"]``.
    """
    glyph = window._tray_glyph or NERD_ICON_PRESETS[0][0]
    ico = _icon_set(glyph)

    tray = QSystemTrayIcon(ico)
    tray.setToolTip("Echo-Node")

    menu = QMenu()

    show_action = menu.addAction("Show / Hide")
    show_action.triggered.connect(lambda: router.on_command({"cmd": "toggle"}))

    # State indicator (read-only menu item, updated dynamically)
    state_action = menu.addAction("● idle")
    state_action.setEnabled(False)

    menu.addSeparator()

    settings_action = menu.addAction("⚙ Settings")
    settings_action.triggered.connect(lambda: window._toggle_settings())

    # Icon submenu
    icon_menu = menu.addMenu("Tray Icon")
    icon_group = []  # prevent GC of QActions
    for idx, (glyph, label, codepoint) in enumerate(NERD_ICON_PRESETS):
        preview = _render_tray_pixmap(glyph, QColor(180, 220, 255, 220), 16)
        a = icon_menu.addAction(QIcon(preview), f"  {label}  ({codepoint})")
        a.setCheckable(True)
        a.setChecked(glyph == window._tray_glyph)
        a._glyph = glyph
        a._nf_idx = idx
        a.triggered.connect(lambda _checked, g=glyph, nm=label: window._set_tray_glyph(g, nm))
        icon_group.append(a)

    menu.addSeparator()

    char_menu = menu.addMenu("Character")
    for ch in window.character_list:
        a = char_menu.addAction(ch.replace("-", " ").title())
        a.triggered.connect(lambda _checked, c=ch: router.on_command({"cmd": "set_character", "name": c}))

    # Nerd Font status
    nf_avail = _nerd_font_available()
    nf_action = menu.addAction(f"{'✓' if nf_avail else '✗'} Nerd Font")
    nf_action.setEnabled(False)
    if not nf_avail:
        install_nf = menu.addAction("Install Nerd Font…")
        install_nf.triggered.connect(lambda: _install_nerd_font_qt(window))

    menu.addSeparator()

    debug_action = menu.addAction("Debug Overlay")
    debug_action.setCheckable(True)
    debug_action.triggered.connect(
        lambda checked: router.on_command({"cmd": "debug_overlay", "enabled": checked})
    )

    menu.addSeparator()

    quit_action = menu.addAction("Quit")
    quit_action.triggered.connect(lambda: router.on_command({"cmd": "quit"}))

    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: router.on_command({"cmd": "toggle"})
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick
        else None
    )

    state_ref: dict[str, Any] = {
        "glyph": glyph,
        "state": "idle",
        "tray": tray,
        "preview_pix": None,
        "state_action": state_action,
        "icon_menu": icon_menu,
        "icon_group": icon_group,
    }
    return tray, state_ref


def _update_tray_icon(state_ref: dict[str, Any], glyph: str | None = None,
                      state: str = "idle") -> None:
    """Call to dynamically update tray icon glyph/color without rebuilding menu."""
    g = glyph or state_ref.get("glyph", NERD_ICON_PRESETS[0][0])
    col = _STATE_COLORS.get(state, _STATE_COLORS["idle"])
    pix = _render_tray_pixmap(g, col, 32)
    ico = QIcon(pix)
    state_ref["tray"].setIcon(ico)
    state_ref["state"] = state
    state_ref["glyph"] = g
    # Update the read-only state action text
    state_action = state_ref.get("state_action")
    if state_action:
        dots = {"idle": "●", "listening": "◉", "transcribing": "◔", "working": "◗", "responding": "▶"}
        state_action.setText(f"{dots.get(state, '●')} {state}")


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
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()

    base = Path(__file__).resolve().parent
    manifest = _load_manifest(base)
    default_character = args.character or manifest.get("default") or next(iter(manifest["characters"]))

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    window = AvatarWindow(base / "frames", manifest, default_character)
    window.show()

    # Set backend options on the SettingsPopup class so all future
    # SettingsPopup instances show the right choices.
    try:
        from echo_node.backends import BACKEND_OPTIONS
        SettingsPopup.set_backend_options(BACKEND_OPTIONS)
    except ImportError:
        pass

    router = CommandRouter(window)

    if args.demo:
        demo_timer = QTimer()
        demo_timer.setInterval(int(4.0 * 1000))
        demo_timer.timeout.connect(lambda: window.start_play(_demo_cues(), 3.5))
        demo_timer.start()
        window.start_play(_demo_cues(), 3.5)
    else:
        # Stdin reader (from controller)
        reader = StdinReader()
        reader.command.connect(router.on_command)
        reader.start()
        # Named pipe (from external scripts like hotkey)
        fifo = FifoReader()
        fifo.command.connect(router.on_command)
        fifo.start()

    # System tray icon
    tray, state_ref = _make_tray_icon(window, router)
    window._tray_state_ref = state_ref
    # Store glyph on each icon action for check-mark tracking
    for a in state_ref.get("icon_group", []):
        idx = state_ref["icon_group"].index(a)
        a._glyph = NERD_ICON_PRESETS[idx][0]
    tray.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
