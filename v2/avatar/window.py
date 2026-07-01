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
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from PyQt6.QtCore import QObject, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGraphicsBlurEffect,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

VISEMES: tuple[str, ...] = ("X", "A", "B", "C", "D", "E", "F", "G", "H")
DEFAULT_SIZE = 220
MARGIN = 16
IDLE_BLINK_PERIOD_S = 4.5

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


# ── Settings popup ───────────────────────────────────────────────────

class SettingsPopup(QFrame):
    """Floating settings panel with HSL colour knobs, shader controls, etc."""

    setting_changed = pyqtSignal(dict)

    def __init__(self, parent: QWidget, character_list: list[str], current_char: str,
                 frame_state: dict[str, Any]):
        super().__init__(parent)
        self.setObjectName("settingsFrame")
        self.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setStyleSheet(POPUP_STYLE)

        self.frame_state = dict(frame_state)
        # Ensure HSL keys exist
        for k in ("hue", "saturation", "lightness", "glow_intensity", "pulse_speed", "pulse_amplitude"):
            self.frame_state.setdefault(k, {
                "hue": DEFAULT_HUE, "saturation": DEFAULT_SATURATION,
                "lightness": DEFAULT_LIGHTNESS, "glow_intensity": DEFAULT_GLOW_INTENSITY,
                "pulse_speed": DEFAULT_PULSE_SPEED, "pulse_amplitude": DEFAULT_PULSE_AMPLITUDE,
            }.get(k))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        # ── Title ──
        title = QLabel("⚙ Avatar Studio")
        title.setObjectName("title")
        layout.addWidget(title)

        # ── Row: Character + Shape ──
        r1 = QHBoxLayout()
        r1.setSpacing(10)

        cc = QVBoxLayout(); cc.addWidget(QLabel("Character"))
        self.combo = QComboBox()
        self.combo.addItems(character_list)
        self.combo.setCurrentText(current_char)
        self.combo.currentTextChanged.connect(lambda n: self._emit("set_character", name=n))
        cc.addWidget(self.combo); r1.addLayout(cc)

        ss = QVBoxLayout(); ss.addWidget(QLabel("Shape"))
        self.shape_combo = QComboBox()
        self.shape_combo.addItems(SHAPES)
        self.shape_combo.setCurrentText(frame_state.get("shape", DEFAULT_SHAPE))
        self.shape_combo.currentTextChanged.connect(self._on_shape)
        ss.addWidget(self.shape_combo); r1.addLayout(ss)
        layout.addLayout(r1)

        # ── HSL: Hue row ──
        self._add_hsl_row(layout, "Hue", 0, 360, "hue", DEFAULT_HUE)
        # ── HSL: Saturation row ──
        self._add_hsl_row(layout, "Sat", 0, 100, "saturation", DEFAULT_SATURATION,
                          fmt=lambda v: f"{v}%")
        # ── HSL: Lightness row ──
        self._add_hsl_row(layout, "Lum", 5, 95, "lightness", DEFAULT_LIGHTNESS,
                          fmt=lambda v: f"{v}%")

        # ── Quick swatches ──
        layout.addWidget(QLabel("Quick Pick"))
        swatch_row = QHBoxLayout()
        swatch_row.setSpacing(3)
        self._swatch_btns: list[QuickColorButton] = []
        for preset in QUICK_COLORS:
            btn = QuickColorButton(preset)
            btn.clicked.connect(lambda _, p=preset: self._on_quick_color(p))
            self._swatch_btns.append(btn)
            swatch_row.addWidget(btn)
        swatch_row.addStretch()
        layout.addLayout(swatch_row)

        # ── Seam ──
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: rgba(100,180,255,0.08);")
        layout.addWidget(sep)

        # ── Row: Opacity + Border ──
        r2 = QHBoxLayout(); r2.setSpacing(10)
        self._add_slider_pair(r2, "BG", 5, 95, "opacity",
                              int(frame_state.get("opacity", DEFAULT_OPACITY) * 100),
                              fmt=lambda v: f"{v}%", cb=self._on_opacity)
        self._add_slider_pair(r2, "Edge", 0, 20, "border_width",
                              int(frame_state.get("border_width", DEFAULT_BORDER_WIDTH) * 2),
                              fmt=lambda v: f"{v/2:.1f}px", cb=self._on_border)
        layout.addLayout(r2)

        # ── Row: Glow + Pulse ──
        r3 = QHBoxLayout(); r3.setSpacing(10)
        self._add_slider_pair(r3, "Glow", 0, 100, "glow_intensity",
                              frame_state.get("glow_intensity", DEFAULT_GLOW_INTENSITY),
                              fmt=lambda v: f"{v}%", cb=self._on_glow)
        self._add_slider_pair(r3, "Pulse", 0, 100, "pulse_speed",
                              int(frame_state.get("pulse_speed", DEFAULT_PULSE_SPEED) * 10),
                              fmt=lambda v: f"{v/10:.1f}s" if v > 0 else "OFF",
                              cb=self._on_pulse)
        layout.addLayout(r3)

        # ── Row: Pulse amplitude ──
        r3b = QHBoxLayout(); r3b.setSpacing(10)
        self._add_slider_pair(r3b, "Wave", 0, 100, "pulse_amplitude",
                              frame_state.get("pulse_amplitude", DEFAULT_PULSE_AMPLITUDE),
                              fmt=lambda v: f"{v}%", cb=self._on_pulse_amp)
        layout.addLayout(r3b)

        # ── Seam ──
        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color: rgba(100,180,255,0.08);")
        layout.addWidget(sep2)

        # ── Row: Size + Vol ──
        r4 = QHBoxLayout(); r4.setSpacing(10)
        self._add_slider_pair(r4, "Size", 100, 400, "size",
                              getattr(parent, '_avatar_size', DEFAULT_SIZE),
                              fmt=lambda v: f"{v}px", cb=self._on_size)
        self._add_slider_pair(r4, "Vol", 0, 100, "volume", 80,
                              fmt=lambda v: f"{v}%",
                              cb=lambda v: (self.vol_val.setText(f"{v}%"),
                                            self._emit("set_volume", value=v / 100)))
        layout.addLayout(r4)

        # ── Row: Mic + Blink ──
        r5 = QHBoxLayout(); r5.setSpacing(10)
        self._add_slider_pair(r5, "Mic", 1, 20, "silence_seconds", 4,
                              fmt=lambda v: f"{v/10:.1f}s",
                              cb=lambda v: (self.silence_val.setText(f"{v/10:.1f}s"),
                                            self._emit("set_silence_seconds", value=v / 10)))
        self._add_slider_pair(r5, "Blink", 10, 100, "blink_interval", 45,
                              fmt=lambda v: f"{v/10:.1f}s",
                              cb=lambda v: (self.blink_val.setText(f"{v/10:.1f}s"),
                                            self._emit("set_blink_interval", value=v / 10)))
        layout.addLayout(r5)

        self.setLayout(layout)
        self.adjustSize()

    # -- helpers: slider builders -------------------------------------------

    def _add_hsl_row(self, parent_layout: QVBoxLayout, label: str,
                     lo: int, hi: int, key: str, default: int,
                     fmt=lambda v: str(v)) -> None:
        row = QHBoxLayout()
        row.setSpacing(6)
        lbl = QLabel(label)
        lbl.setFixedWidth(28)
        row.addWidget(lbl)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(lo, hi)
        slider.setValue(self.frame_state.get(key, default))
        val_label = QLabel(fmt(slider.value()))
        val_label.setObjectName("value")
        slider.valueChanged.connect(
            lambda v, k=key, vl=val_label, f=fmt: (
                vl.setText(f(v)),
                self.frame_state.__setitem__(k, v),
                self._emit("set_frame_style", **self.frame_state)
            )
        )
        row.addWidget(slider, stretch=1)
        row.addWidget(val_label)
        setattr(self, f"{key}_slider", slider)
        setattr(self, f"{key}_val", val_label)
        parent_layout.addLayout(row)

    def _add_slider_pair(self, parent_layout: QHBoxLayout, label: str,
                         lo: int, hi: int, key: str, default: int,
                         fmt=lambda v: str(v),
                         cb=None) -> None:
        col = QVBoxLayout()
        col.setSpacing(2)
        row = QHBoxLayout()
        row.setSpacing(4)
        lbl = QLabel(label)
        row.addWidget(lbl)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(lo, hi)
        slider.setValue(default)
        val_label = QLabel(fmt(default))
        val_label.setObjectName("value")
        if cb:
            slider.valueChanged.connect(lambda v, vl=val_label, f=fmt, c=cb: (vl.setText(f(v)), c(v)))
        else:
            slider.valueChanged.connect(
                lambda v, k=key, vl=val_label, f=fmt: (
                    vl.setText(f(v)),
                    self.frame_state.__setitem__(k, v),
                    self._emit("set_frame_style", **self.frame_state)
                )
            )
        row.addWidget(slider, stretch=1)
        row.addWidget(val_label)
        col.addLayout(row)
        setattr(self, f"{key}_slider", slider)
        setattr(self, f"{key}_val", val_label)
        parent_layout.addLayout(col)

    # -- event handlers -----------------------------------------------------

    def _emit(self, cmd: str, **kw: Any) -> None:
        payload = {"cmd": cmd, **kw}
        self.setting_changed.emit(payload)
        print(json.dumps(payload), flush=True)

    def _on_shape(self, shape: str) -> None:
        self.frame_state["shape"] = shape
        self._emit("set_frame_style", **self.frame_state)

    def _on_quick_color(self, preset: dict[str, Any]) -> None:
        self.frame_state["hue"] = preset["hue"]
        self.frame_state["saturation"] = preset["sat"]
        self.frame_state["lightness"] = preset["lig"]
        for btn in self._swatch_btns:
            btn.setChecked(btn.preset is preset)
        # Sync sliders
        self.hue_slider.setValue(preset["hue"])
        self.hue_val.setText(str(preset["hue"]))
        self.saturation_slider.setValue(preset["sat"])
        self.saturation_val.setText(f'{preset["sat"]}%')
        self.lightness_slider.setValue(preset["lig"])
        self.lightness_val.setText(f'{preset["lig"]}%')
        self._emit("set_frame_style", **self.frame_state)

    def _on_border(self, val: int) -> None:
        self.frame_state["border_width"] = val / 2
        self._emit("set_frame_style", **self.frame_state)

    def _on_opacity(self, val: int) -> None:
        self.frame_state["opacity"] = val / 100
        self._emit("set_frame_style", **self.frame_state)

    def _on_glow(self, val: int) -> None:
        self.frame_state["glow_intensity"] = val
        self._emit("set_frame_style", **self.frame_state)

    def _on_pulse(self, val: int) -> None:
        self.frame_state["pulse_speed"] = val / 10
        self._emit("set_frame_style", **self.frame_state)

    def _on_pulse_amp(self, val: int) -> None:
        self.frame_state["pulse_amplitude"] = val
        self._emit("set_frame_style", **self.frame_state)

    def _on_size(self, val: int) -> None:
        self._emit("set_size", value=val)

    # -- sync from external state -------------------------------------------

    def sync_frame_state(self, state: dict[str, Any]) -> None:
        self.frame_state.update(state)
        for key, slider_attr, val_attr, fmt in [
            ("shape", None, None, None),
            ("hue", "hue_slider", "hue_val", str),
            ("saturation", "saturation_slider", "saturation_val", lambda v: f"{v}%"),
            ("lightness", "lightness_slider", "lightness_val", lambda v: f"{v}%"),
            ("opacity", "opacity_slider", "opacity_val", lambda v: f"{v}%"),
            ("border_width", "border_slider", "border_val", lambda v: f"{v/2:.1f}px"),
            ("glow_intensity", "glow_slider", "glow_val", lambda v: f"{v}%"),
            ("pulse_speed", "pulse_speed_slider", "pulse_speed_val",
             lambda v: f"{v/10:.1f}s" if v > 0 else "OFF"),
            ("pulse_amplitude", "pulse_amplitude_slider", "pulse_amplitude_val", lambda v: f"{v}%"),
        ]:
            if key not in state:
                continue
            slider = getattr(self, slider_attr, None) if slider_attr else None
            v = state[key]
            if key == "border_width":
                v = int(state["border_width"] * 2)
            elif key == "opacity":
                v = int(state["opacity"] * 100)
            elif key == "pulse_speed":
                v = int(state["pulse_speed"] * 10)
            if slider:
                slider.blockSignals(True)
                slider.setValue(v)
                slider.blockSignals(False)
            if val_attr:
                lbl = getattr(self, val_attr, None)
                if lbl:
                    lbl.setText(fmt(v) if fmt else str(v))

    def show_at(self, x: int, y: int) -> None:
        """Position popup to the left of the avatar window, top-aligned."""
        parent = self.parent()
        if parent and hasattr(parent, 'mapToGlobal'):
            parent_pos = parent.mapToGlobal(parent.rect().topLeft())
            px = max(8, parent_pos.x() - self.width())
            py = parent_pos.y()
        else:
            # Fallback: above-left of the settings button
            px = max(8, x - self.width())
            py = max(8, y - self.height())
        # Clamp so popup doesn't go off-screen left
        screen = QGuiApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            px = max(geo.x() + 4, px)
            if px + self.width() > geo.right():
                px = geo.right() - self.width() - 4
            py = max(geo.y() + 4, min(py, geo.bottom() - self.height() - 4))
        self.move(px, py)
        self.show()


# ── Debug overlay widget ───────────────────────────────────────────

class _DebugOverlay(QWidget):
    """Small waveform + threshold lines rendered inside the avatar frame.

    Shows a scrolling RMS waveform with VAD threshold and boosted-threshold
    lines, plus text labels for the current values. Toggled via:
        {"cmd":"debug_overlay", "enabled":true}
    Updated via:
        {"cmd":"debug_update", "vad":0.45, "rms":600, "threshold":0.40,
         "boosted_threshold":0.54, "rms_floor":500, "boosted_rms":800,
         "state":"playing"}
    """

    def __init__(self, parent: QWidget,
                 data_ref: dict[str, float],
                 history_ref: list[float]):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._data = data_ref
        self._history = history_ref
        self._max_history = 120

    def paintEvent(self, event):
        if not self._data:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        if w < 10 or h < 10:
            painter.end()
            return

        # Dark background with rounded corners
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 160))
        painter.drawRoundedRect(0, 0, w, h, 6, 6)

        d = self._data
        vad = d.get("vad", 0.0)
        rms = d.get("rms", 0.0)
        threshold = d.get("threshold", 0.40)
        boosted = d.get("boosted_threshold", 0.54)
        rms_floor = d.get("rms_floor", 500)
        boosted_rms = d.get("boosted_rms", 800)
        state = d.get("state", "idle")

        # Layout: state label on left, VAD bar in middle, RMS bar on right,
        # thin waveform along bottom
        margin = 4
        lh = 12  # label height
        bar_h = h - lh - margin * 2
        third = (w - margin * 2) // 2

        # ── VAD bar (left half) ──
        vx = margin
        vw = third - 2
        # Background track
        painter.setBrush(QColor(40, 40, 60, 120))
        painter.drawRoundedRect(vx, margin, vw, bar_h, 3, 3)
        # Threshold line
        ty = margin + int(bar_h * (1.0 - threshold))
        painter.setPen(QPen(QColor(100, 255, 100, 120), 1))
        painter.drawLine(vx, ty, vx + vw, ty)
        painter.setPen(QPen(QColor(100, 255, 100, 80), 1))
        painter.drawText(vx + 2, ty - 2, f"T{threshold:.2f}")

        # Boosted threshold line
        by = margin + int(bar_h * (1.0 - min(1.0, boosted)))
        painter.setPen(QPen(QColor(255, 200, 80, 150), 1))
        painter.drawLine(vx, by, vx + vw, by)
        painter.setPen(QPen(QColor(255, 200, 80, 80), 1))
        painter.drawText(vx + 2, by - 2, f"B{boosted:.2f}")

        # VAD fill
        fill_h = max(2, int(bar_h * vad))
        fill_y = margin + bar_h - fill_h
        vad_color = QColor(80, 200, 255, 180)
        if vad >= boosted:
            vad_color = QColor(255, 120, 80, 200)
        elif vad >= threshold:
            vad_color = QColor(255, 200, 80, 180)
        painter.setBrush(vad_color)
        painter.drawRoundedRect(vx + 1, fill_y, vw - 2, fill_h, 2, 2)

        painter.setPen(QColor(180, 220, 255, 180))
        painter.drawText(vx + 2, margin + bar_h + lh - 2, f"VAD {vad:.2f}")

        # ── RMS bar (right half) ──
        rx = vx + vw + 4
        rw = third - 2
        max_rms = max(2000, boosted_rms * 2)
        painter.setBrush(QColor(40, 40, 60, 120))
        painter.drawRoundedRect(rx, margin, rw, bar_h, 3, 3)

        # RMS floor line
        rfy = margin + int(bar_h * (1.0 - min(1.0, rms_floor / max_rms)))
        painter.setPen(QPen(QColor(100, 255, 100, 120), 1))
        painter.drawLine(rx, rfy, rx + rw, rfy)
        painter.setPen(QPen(QColor(100, 255, 100, 80), 1))
        painter.drawText(rx + 2, rfy - 2, f"R{rms_floor:.0f}")

        # Boosted RMS line
        brfy = margin + int(bar_h * (1.0 - min(1.0, boosted_rms / max_rms)))
        painter.setPen(QPen(QColor(255, 200, 80, 150), 1))
        painter.drawLine(rx, brfy, rx + rw, brfy)
        painter.setPen(QPen(QColor(255, 200, 80, 80), 1))
        painter.drawText(rx + 2, brfy - 2, f"BR{boosted_rms:.0f}")

        # RMS fill
        rms_norm = min(1.0, rms / max_rms)
        rfill_h = max(2, int(bar_h * rms_norm))
        rfill_y = margin + bar_h - rfill_h
        rms_color = QColor(80, 200, 255, 180)
        if rms >= boosted_rms:
            rms_color = QColor(255, 120, 80, 200)
        elif rms >= rms_floor:
            rms_color = QColor(255, 200, 80, 180)
        painter.setBrush(rms_color)
        painter.drawRoundedRect(rx + 1, rfill_y, rw - 2, rfill_h, 2, 2)

        painter.setPen(QColor(180, 220, 255, 180))
        painter.drawText(rx + 2, margin + bar_h + lh - 2, f"RMS {rms:.0f}")

        # ── State label ──
        painter.setPen(QColor(255, 255, 255, 200))
        font = QFont("monospace", 8)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(self.width() - 60, margin + lh, state.upper())

        # ── Scrolling waveform (thin line at bottom of bars) ──
        if len(self._history) > 1:
            wave_y = margin + bar_h + 2
            wave_h = lh - 6
            painter.setPen(QPen(QColor(100, 180, 255, 120), 1))
            path = QPainterPath()
            hist = self._history[-self._max_history:]
            step_x = min(rx + rw - rx, self._max_history) / len(hist)
            for i, val in enumerate(hist):
                norm = min(1.0, val / max_rms)
                px = rx + i * step_x
                py = wave_y + wave_h - norm * wave_h
                if i == 0:
                    path.moveTo(px, py)
                else:
                    path.lineTo(px, py)
            painter.drawPath(path)

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

        self.frames_root = frames_root
        self.manifest = manifest
        self.character_list = list(manifest.get("characters", {}).keys())
        self.character: str = ""
        self.frames: dict[str, QPixmap] = {}
        self._avatar_size = DEFAULT_SIZE

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

        # Outer frame widget
        self.frame_widget = QFrame(self)
        self.frame_widget.setGraphicsEffect(self._glow_effect)
        self._apply_frame_style()

        # Layout inside frame
        frame_layout = QVBoxLayout(self.frame_widget)
        frame_layout.setContentsMargins(8, 8, 8, 8)
        frame_layout.setSpacing(4)

        # Avatar sprite
        self.label = QLabel()
        self.label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.label.setStyleSheet("background: transparent;")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame_layout.addWidget(self.label, stretch=1)

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

        # ── Debug overlay (VAD/RMS waveform) ──
        self._debug_enabled = False
        self._debug_data: dict[str, float] = {
            "vad": 0.0, "rms": 0.0, "threshold": 0.40,
            "boosted_threshold": 0.54, "rms_floor": 500,
            "boosted_rms": 800, "state": "idle",
        }
        self._debug_history: list[float] = []  # RMS history for waveform
        self._debug_timer = QTimer(self)
        self._debug_timer.setInterval(100)  # 10 fps refresh
        self._debug_timer.timeout.connect(self._debug_repaint)
        # Overlay widget for painting
        self._debug_overlay = _DebugOverlay(self.frame_widget, self._debug_data, self._debug_history)
        self._debug_overlay.hide()

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
        """Frame border: bright with moderate alpha."""
        b_lig = min(100, self._lightness + 25)
        b_alpha = max(0.15, 0.25 + (self._lightness / 200))
        return hsl_css(self._hue, self._saturation, b_lig, b_alpha)

    def _get_glow_color(self) -> QColor:
        """The glow shadow colour (QColor, not CSS)."""
        c = QColor()
        glow_lig = min(100, self._lightness + 10)
        intensity = max(0.01, self._glow_intensity / 100)
        c.setHsl(self._hue % 360,
                 max(0, min(255, self._saturation * 255 // 100)),
                 max(0, min(255, glow_lig * 255 // 100)),
                 max(0, min(255, int(180 * intensity))))
        return c

    def _get_glow_blur(self) -> int:
        """Map glow_intensity to blur radius: 5-60px."""
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

    # ── Debug overlay ───────────────────────────────────────────────────

    def _debug_repaint(self) -> None:
        """Called by _debug_timer to refresh the overlay."""
        if self._debug_enabled and self._debug_overlay:
            self._debug_overlay.update()

    def set_debug_enabled(self, enabled: bool) -> None:
        self._debug_enabled = enabled
        self._debug_overlay.setVisible(enabled)
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
        # Reposition debug overlay within the frame
        if hasattr(self, '_debug_overlay'):
            inset = 4
            ow = self.frame_widget.width() - inset * 2
            oh = 52
            self._debug_overlay.setGeometry(inset,
                                             self.frame_widget.height() - oh - inset,
                                             ow, oh)

    def _anchor_bottom_right(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.x() + geo.width() - self.width() - MARGIN
        y = geo.y() + geo.height() - self.height() - MARGIN - 40
        self.move(x, y)

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

    def _restart_idle_blink(self) -> None:
        self._idle_blink.stop()
        if self._blink_interval > 0:
            self._idle_blink.setInterval(int(self._blink_interval * 1000))
            self._idle_blink.start()

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
        self.frames = {}
        self.set_character(self.character)
        self._update_window_size()
        self._anchor_bottom_right()

    # ── Viseme rendering ─────────────────────────────────────────────────

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
        elif cmd == "hide":
            self.window.hide()
        elif cmd == "debug_overlay":
            self.window.set_debug_enabled(bool(payload.get("enabled", False)))
        elif cmd == "debug_update":
            self.window.update_debug_data(**{
                k: v for k, v in payload.items()
                if k in ("vad", "rms", "threshold", "boosted_threshold",
                         "rms_floor", "boosted_rms", "state")
            })
        elif cmd == "quit":
            QApplication.instance().quit()
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
    parser.add_argument("--demo", action="store_true")
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
