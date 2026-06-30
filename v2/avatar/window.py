"""Floating avatar window — runs as its own process to keep the Qt event loop
clear of the assistant's audio/STT loops.

Protocol (line-delimited JSON on stdin, one object per line):

    {"cmd":"set_character", "name":"raccoon-hacker"}
    {"cmd":"set_frame_style", "shape":"rounded", "color":"blue", "opacity":0.4, "border_width":2}
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
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
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

# ── Default frame style ─────────────────────────────────────────────

FRAME_PRESETS: dict[str, dict[str, Any]] = {
    "blue":  {"bg": "rgba(10,10,30,{opacity})",  "border": "rgba(80,160,255,{alpha})",  "glow": "rgba(80,160,255,0.08)"},
    "green": {"bg": "rgba(10,30,10,{opacity})",  "border": "rgba(80,220,120,{alpha})",  "glow": "rgba(80,220,120,0.08)"},
    "purple":{"bg": "rgba(25,10,35,{opacity})",  "border": "rgba(180,80,255,{alpha})",  "glow": "rgba(180,80,255,0.08)"},
    "amber": {"bg": "rgba(30,20,5,{opacity})",   "border": "rgba(255,180,40,{alpha})", "glow": "rgba(255,180,40,0.08)"},
    "red":   {"bg": "rgba(35,10,10,{opacity})",  "border": "rgba(255,80,80,{alpha})",   "glow": "rgba(255,80,80,0.08)"},
    "cyan":  {"bg": "rgba(5,25,30,{opacity})",   "border": "rgba(40,220,255,{alpha})",  "glow": "rgba(40,220,255,0.08)"},
    "pink":  {"bg": "rgba(30,10,25,{opacity})",  "border": "rgba(255,100,180,{alpha})", "glow": "rgba(255,100,180,0.08)"},
    "white": {"bg": "rgba(20,20,30,{opacity})",  "border": "rgba(200,220,255,{alpha})",  "glow": "rgba(200,220,255,0.08)"},
}

SHAPES = ["square", "rounded", "circle"]
DEFAULT_SHAPE = "rounded"
DEFAULT_COLOR = "blue"
DEFAULT_OPACITY = 0.55
DEFAULT_BORDER_WIDTH = 1.5

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
        background: rgba(15,15,35,0.92);
        border: 1px solid rgba(100,160,255,0.25);
        border-radius: 14px;
    }
    QLabel {
        color: #cce;
        font-size: 10px;
        font-weight: bold;
    }
    QLabel#title {
        font-size: 13px;
        color: #eef;
    }
    QLabel#value {
        font-size: 10px;
        color: #99b;
        min-width: 30px;
    }
    QComboBox {
        background: rgba(40,40,70,0.80);
        color: #dde;
        border: 1px solid rgba(100,180,255,0.25);
        border-radius: 6px;
        padding: 3px 8px;
        font-size: 10px;
        min-width: 90px;
    }
    QComboBox::drop-down { border: none; }
    QComboBox QAbstractItemView {
        background: rgba(20,20,45,0.96);
        color: #dde;
        selection-background-color: rgba(100,180,255,0.25);
        border: 1px solid rgba(100,180,255,0.2);
        border-radius: 4px;
        outline: none;
    }
    QSlider::groove:horizontal {
        height: 3px;
        background: rgba(60,60,100,0.5);
        border-radius: 2px;
    }
    QSlider::handle:horizontal {
        background: rgba(100,180,255,0.80);
        width: 10px;
        height: 10px;
        margin: -3px 0;
        border-radius: 5px;
    }
    QSlider::sub-page:horizontal {
        background: rgba(100,180,255,0.30);
        border-radius: 2px;
    }
"""


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


# ── Color swatch button ─────────────────────────────────────────────

class ColorButton(QPushButton):
    def __init__(self, color_name: str, preset: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.color_name = color_name
        self.preset = preset
        self.setCheckable(True)
        self.setFixedSize(22, 22)
        border_color = preset["border"].format(alpha=1.0, opacity=1.0)
        self.setStyleSheet(f"""
            QPushButton {{
                background: {preset["bg"].format(opacity=0.7)};
                border: 2px solid {border_color};
                border-radius: 11px;
            }}
            QPushButton:hover {{
                border: 2px solid white;
            }}
            QPushButton:checked {{
                border: 2.5px solid white;
                background: {preset["bg"].format(opacity=0.9)};
            }}
        """)


# ── Settings popup ───────────────────────────────────────────────────

class SettingsPopup(QFrame):
    """Floating settings panel with knobs for everything."""

    # Signals to send changes back to the host process
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
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(POPUP_STYLE)

        self.frame_state = dict(frame_state)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        # ── Title ──
        title = QLabel("⚙ Avatar")
        title.setObjectName("title")
        layout.addWidget(title)

        # ── Row: Character + Shape ──
        row1 = QHBoxLayout()
        row1.setSpacing(10)

        cc = QVBoxLayout()
        cc.addWidget(QLabel("Character"))
        self.combo = QComboBox()
        self.combo.addItems(character_list)
        self.combo.setCurrentText(current_char)
        self.combo.currentTextChanged.connect(lambda n: self._emit("set_character", name=n))
        cc.addWidget(self.combo)
        row1.addLayout(cc)

        ss = QVBoxLayout()
        ss.addWidget(QLabel("Shape"))
        self.shape_combo = QComboBox()
        self.shape_combo.addItems(SHAPES)
        self.shape_combo.setCurrentText(frame_state.get("shape", DEFAULT_SHAPE))
        self.shape_combo.currentTextChanged.connect(self._on_shape)
        ss.addWidget(self.shape_combo)
        row1.addLayout(ss)
        layout.addLayout(row1)

        # ── Color swatches ──
        layout.addWidget(QLabel("Color"))
        color_grid = QHBoxLayout()
        color_grid.setSpacing(4)
        self.color_btns: dict[str, ColorButton] = {}
        self._color_group: list[ColorButton] = []
        for cname in FRAME_PRESETS:
            btn = ColorButton(cname, FRAME_PRESETS[cname])
            btn.clicked.connect(lambda _, n=cname: self._on_color(n))
            self.color_btns[cname] = btn
            self._color_group.append(btn)
            color_grid.addWidget(btn)
        color_grid.addStretch()
        layout.addLayout(color_grid)

        # ── Sliders row 1: Opacity + Border ──
        row3 = QHBoxLayout()
        row3.setSpacing(12)

        # Opacity
        op_v = QVBoxLayout()
        op_h = QHBoxLayout()
        op_lbl = QLabel("BG")
        op_h.addWidget(op_lbl)
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(5, 95)
        self.opacity_slider.setValue(int(frame_state.get("opacity", DEFAULT_OPACITY) * 100))
        self.opacity_slider.valueChanged.connect(self._on_opacity)
        op_h.addWidget(self.opacity_slider)
        self.opacity_val = QLabel(f'{self.opacity_slider.value()}%')
        self.opacity_val.setObjectName("value")
        op_h.addWidget(self.opacity_val)
        op_v.addLayout(op_h)
        row3.addLayout(op_v)

        # Border width
        bw_v = QVBoxLayout()
        bw_h = QHBoxLayout()
        bw_lbl = QLabel("Edge")
        bw_h.addWidget(bw_lbl)
        self.border_slider = QSlider(Qt.Orientation.Horizontal)
        self.border_slider.setRange(0, 20)
        self.border_slider.setValue(int(frame_state.get("border_width", DEFAULT_BORDER_WIDTH) * 2))
        self.border_slider.valueChanged.connect(self._on_border)
        bw_h.addWidget(self.border_slider)
        self.border_val = QLabel(f'{self.border_slider.value() // 2}.{self.border_slider.value() % 2 * 5}px')
        self.border_val.setObjectName("value")
        bw_h.addWidget(self.border_val)
        bw_v.addLayout(bw_h)
        row3.addLayout(bw_v)
        layout.addLayout(row3)

        # ── Separator ──
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: rgba(100,180,255,0.10);")
        layout.addWidget(sep)

        # ── Sliders row 2: Size + Volume ──
        row4 = QHBoxLayout()
        row4.setSpacing(12)

        # Size
        sz_v = QVBoxLayout()
        sz_h = QHBoxLayout()
        sz_lbl = QLabel("Size")
        sz_h.addWidget(sz_lbl)
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(100, 400)
        self.size_slider.setValue(parent._avatar_size if hasattr(parent, '_avatar_size') else DEFAULT_SIZE)
        self.size_slider.valueChanged.connect(self._on_size)
        sz_h.addWidget(self.size_slider)
        self.size_val = QLabel(f'{self.size_slider.value()}px')
        self.size_val.setObjectName("value")
        sz_h.addWidget(self.size_val)
        sz_v.addLayout(sz_h)
        row4.addLayout(sz_v)

        # Volume
        vl_v = QVBoxLayout()
        vl_h = QHBoxLayout()
        vl_lbl = QLabel("Vol")
        vl_h.addWidget(vl_lbl)
        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(80)
        self.vol_slider.valueChanged.connect(lambda v: (self.vol_val.setText(f'{v}%'), self._emit("set_volume", value=v/100)))
        vl_h.addWidget(self.vol_slider)
        self.vol_val = QLabel('80%')
        self.vol_val.setObjectName("value")
        vl_h.addWidget(self.vol_val)
        vl_v.addLayout(vl_h)
        row4.addLayout(vl_v)
        layout.addLayout(row4)

        # ── Sliders row 3: Silence + Blink ──
        row5 = QHBoxLayout()
        row5.setSpacing(12)

        # Silence threshold
        si_v = QVBoxLayout()
        si_h = QHBoxLayout()
        si_lbl = QLabel("Mic")
        si_h.addWidget(si_lbl)
        self.silence_slider = QSlider(Qt.Orientation.Horizontal)
        self.silence_slider.setRange(1, 20)
        self.silence_slider.setValue(4)
        self.silence_slider.valueChanged.connect(lambda v: (self.silence_val.setText(f'{v/10:.1f}s'), self._emit("set_silence_seconds", value=v/10)))
        si_h.addWidget(self.silence_slider)
        self.silence_val = QLabel('0.4s')
        self.silence_val.setObjectName("value")
        si_h.addWidget(self.silence_val)
        si_v.addLayout(si_h)
        row5.addLayout(si_v)

        # Blink interval
        bl_v = QVBoxLayout()
        bl_h = QHBoxLayout()
        bl_lbl = QLabel("Blink")
        bl_h.addWidget(bl_lbl)
        self.blink_slider = QSlider(Qt.Orientation.Horizontal)
        self.blink_slider.setRange(10, 100)
        self.blink_slider.setValue(45)
        self.blink_slider.valueChanged.connect(lambda v: (self.blink_val.setText(f'{v/10:.1f}s'), self._emit("set_blink_interval", value=v/10)))
        bl_h.addWidget(self.blink_slider)
        self.blink_val = QLabel('4.5s')
        self.blink_val.setObjectName("value")
        bl_h.addWidget(self.blink_val)
        bl_v.addLayout(bl_h)
        row5.addLayout(bl_v)
        layout.addLayout(row5)

        self.setLayout(layout)
        self.adjustSize()

    # -- helpers -------------------------------------------------------------

    def _emit(self, cmd: str, **kw: Any) -> None:
        payload = {"cmd": cmd, **kw}
        self.setting_changed.emit(payload)
        # Also send to stdout so the controller can pick it up
        print(json.dumps(payload), flush=True)

    def _on_shape(self, shape: str) -> None:
        self.frame_state["shape"] = shape
        self._emit("set_frame_style", **self.frame_state)

    def _on_color(self, name: str) -> None:
        self.frame_state["color"] = name
        for btn in self._color_group:
            btn.setChecked(btn.color_name == name)
        self._emit("set_frame_style", **self.frame_state)

    def _on_opacity(self, val: int) -> None:
        self.opacity_val.setText(f'{val}%')
        self.frame_state["opacity"] = val / 100
        self._emit("set_frame_style", **self.frame_state)

    def _on_border(self, val: int) -> None:
        px = val / 2
        self.border_val.setText(f'{px:.1f}px')
        self.frame_state["border_width"] = px
        self._emit("set_frame_style", **self.frame_state)

    def _on_size(self, val: int) -> None:
        self.size_val.setText(f'{val}px')
        self._emit("set_size", value=val)

    def sync_frame_state(self, state: dict[str, Any]) -> None:
        self.frame_state.update(state)
        if "shape" in state:
            self.shape_combo.blockSignals(True)
            self.shape_combo.setCurrentText(state["shape"])
            self.shape_combo.blockSignals(False)
        if "color" in state:
            for btn in self._color_group:
                btn.setChecked(btn.color_name == state["color"])
        if "opacity" in state:
            self.opacity_slider.blockSignals(True)
            self.opacity_slider.setValue(int(state["opacity"] * 100))
            self.opacity_slider.blockSignals(False)
            self.opacity_val.setText(f'{int(state["opacity"] * 100)}%')
        if "border_width" in state:
            v = int(state["border_width"] * 2)
            self.border_slider.blockSignals(True)
            self.border_slider.setValue(v)
            self.border_slider.blockSignals(False)
            self.border_val.setText(f'{state["border_width"]:.1f}px')

    def show_at(self, x: int, y: int) -> None:
        self.move(max(0, x - self.width()), max(0, y - self.height()))
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

        # ── Frame style state ──
        self._frame_shape = DEFAULT_SHAPE
        self._frame_color = DEFAULT_COLOR
        self._frame_opacity = DEFAULT_OPACITY
        self._frame_border_width = DEFAULT_BORDER_WIDTH

        # ── Blink ──
        self._blink_interval = IDLE_BLINK_PERIOD_S

        # Root styling
        self.setStyleSheet("background: transparent;")

        # Outer frame widget
        self.frame_widget = QFrame(self)
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
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setContentsMargins(2, 0, 2, 2)
        ctrl_layout.setSpacing(4)

        self.char_label = QLabel()
        self.char_label.setStyleSheet("color: rgba(180,200,255,0.55); font-size: 9px; font-weight: bold; padding: 0 4px;")
        self.char_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        ctrl_layout.addWidget(self.char_label, stretch=1)

        self.prev_btn = QPushButton("◀")
        self.prev_btn.setStyleSheet(BTN_STYLE)
        self.prev_btn.setToolTip("Previous character")
        self.prev_btn.clicked.connect(self._prev_character)
        ctrl_layout.addWidget(self.prev_btn)

        self.next_btn = QPushButton("▶")
        self.next_btn.setStyleSheet(BTN_STYLE)
        self.next_btn.setToolTip("Next character")
        self.next_btn.clicked.connect(self._next_character)
        ctrl_layout.addWidget(self.next_btn)

        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setStyleSheet(BTN_STYLE)
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.clicked.connect(self._toggle_settings)
        ctrl_layout.addWidget(self.settings_btn)

        frame_layout.addLayout(ctrl_layout)

        # Total size calc
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

        # Settings popup
        self._settings_popup: SettingsPopup | None = None

        self.set_character(default_character)
        self._anchor_bottom_right()

    # -- frame styling -------------------------------------------------------

    def _make_frame_css(self) -> str:
        preset = FRAME_PRESETS.get(self._frame_color, FRAME_PRESETS["blue"])
        bg = preset["bg"].format(opacity=self._frame_opacity)
        border_c = preset["border"].format(alpha=0.35, opacity=self._frame_opacity)
        glow = preset["glow"].format(opacity=self._frame_opacity, alpha=self._frame_opacity)

        r = 0
        if self._frame_shape == "rounded":
            r = 18
        elif self._frame_shape == "circle":
            r = 999  # fully rounded = circle when square

        bw = max(0.5, self._frame_border_width)
        return f"""
            QFrame {{
                background: {bg};
                border: {bw}px solid {border_c};
                border-radius: {r}px;
            }}
        """

    def _apply_frame_style(self) -> None:
        self.frame_widget.setStyleSheet(self._make_frame_css())

    def set_frame_style(self, **kw: Any) -> None:
        changed = False
        if "shape" in kw and kw["shape"] in SHAPES and kw["shape"] != self._frame_shape:
            self._frame_shape = kw["shape"]
            changed = True
        if "color" in kw and kw["color"] in FRAME_PRESETS and kw["color"] != self._frame_color:
            self._frame_color = kw["color"]
            changed = True
        if "opacity" in kw:
            self._frame_opacity = max(0.05, min(1.0, float(kw["opacity"])))
            changed = True
        if "border_width" in kw:
            self._frame_border_width = max(0, min(10, float(kw["border_width"])))
            changed = True
        if changed:
            self._apply_frame_style()

    def _frame_state_dict(self) -> dict[str, Any]:
        return {
            "shape": self._frame_shape,
            "color": self._frame_color,
            "opacity": self._frame_opacity,
            "border_width": self._frame_border_width,
        }

    # -- window sizing -------------------------------------------------------

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

    # -- settings popup ------------------------------------------------------

    def _toggle_settings(self) -> None:
        if self._settings_popup and self._settings_popup.isVisible():
            self._settings_popup.close()
            return
        button_pos = self.settings_btn.mapToGlobal(self.settings_btn.rect().topLeft())
        self._settings_popup = SettingsPopup(
            self, self.character_list, self.character, self._frame_state_dict()
        )
        self._settings_popup.setting_changed.connect(self._on_setting_change)
        self._settings_popup.show_at(button_pos.x(), button_pos.y())

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
        if self._settings_popup and self._settings_popup.isVisible():
            self._settings_popup.size_val.setText(f'{size}px')

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
