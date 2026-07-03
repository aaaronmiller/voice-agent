"""Tabbed settings popup for Echo-Node avatar.

Replaces the old single-panel SettingsPopup with 4 tabs:
  - Display: existing visual controls (HSL, glow, character, etc.)
  - Agent: LLM, STT, TTS provider/model/api config
  - Cloud: LiveKit, LemonSlice, Gemini config
  - Profiles: save/load named config snapshots

IPC: all settings emit via the same setting_changed signal → stdout JSON
→ controller → assistant_v2._on_setting_from_avatar().
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QPointF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

# ── Profiles directory ───────────────────────────────────────────

PROFILES_DIR = Path(__file__).resolve().parent.parent / "profiles"
PROFILES_DIR.mkdir(exist_ok=True)


# ── Styling ──────────────────────────────────────────────────────

TAB_STYLE = """
    QTabWidget::pane { border: none; background: transparent; }
    QTabBar::tab { background: rgba(40,45,80,0.6); color: #889;
                   padding: 4px 12px; border-radius: 4px;
                   margin-right: 2px; font-size: 11px; }
    QTabBar::tab:selected { background: rgba(80,100,180,0.5); color: #dde; }
    QTabBar::tab:hover { background: rgba(60,70,120,0.6); color: #aab; }
    QGroupBox { font-weight: bold; border: 1px solid rgba(80,100,180,0.25);
                border-radius: 6px; margin-top: 8px; padding: 12px 8px 8px; }
    QGroupBox::title { subcontrol-origin: margin; padding: 0 6px; color: #aab; }
    QLineEdit, QComboBox, QSpinBox {
        background: rgba(20,25,50,0.8); color: #dde; border: 1px solid rgba(80,100,180,0.3);
        border-radius: 4px; padding: 3px 6px; min-height: 20px; }
    QPushButton {
        background: rgba(40,50,100,0.6); color: #dde; border: 1px solid rgba(80,100,180,0.3);
        border-radius: 4px; padding: 4px 12px; font-size: 11px; }
    QPushButton:hover { background: rgba(60,80,160,0.6); }
    QLabel { color: #aab; font-size: 11px; }
"""


# ── Settings Popup ───────────────────────────────────────────────

class SettingsPopup(QFrame):
    """Floating tabbed settings panel for full avatar + agent configuration."""

    setting_changed = pyqtSignal(dict)

    # Class-level backend options (set by avatar window)
    _backend_options: list[tuple[str, str, str]] = []
    _backend_default: str = "hermes"

    def __init__(self, parent: QWidget, character_list: list[str],
                 current_char: str, frame_state: dict[str, Any]):
        super().__init__(parent)
        self.setObjectName("settingsFrame")
        self.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(TAB_STYLE)
        self.setMinimumWidth(340)

        # Frame state for display tab
        self.frame_state = dict(frame_state)
        for k in ("hue", "saturation", "lightness",
                  "glow_intensity", "pulse_speed", "pulse_amplitude"):
            self.frame_state.setdefault(k, {
                "hue": 200, "saturation": 70, "lightness": 45,
                "glow_intensity": 50, "pulse_speed": 3.0, "pulse_amplitude": 30,
            }.get(k, 0))

        # Build UI
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        title = QLabel("\u2699 Avatar Studio")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #dde; padding: 2px 0;")
        layout.addWidget(title)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(TAB_STYLE)

        self.tabs.addTab(self._build_display_tab(character_list, current_char), "Display")
        self.tabs.addTab(self._build_agent_tab(), "Agent")
        self.tabs.addTab(self._build_cloud_tab(), "Cloud")
        self.tabs.addTab(self._build_profiles_tab(), "Presets")

        layout.addWidget(self.tabs, stretch=1)
        self.setLayout(layout)
        self.adjustSize()

    # ═══════════════════════════════════════════════════════════════
    #  Tab 1: Display
    # ═══════════════════════════════════════════════════════════════

    def _build_display_tab(self, chars: list[str], cur_char: str) -> QWidget:
        tab = QWidget()
        lo = QVBoxLayout(tab)
        lo.setContentsMargins(0, 4, 0, 0)
        lo.setSpacing(4)

        # Character + Shape row
        r1 = QHBoxLayout(); r1.setSpacing(8)
        cc = QVBoxLayout(); cc.addWidget(QLabel("Character"))
        self.combo = QComboBox()
        self.combo.addItems(chars)
        self.combo.setCurrentText(cur_char)
        self.combo.currentTextChanged.connect(lambda n: self._emit("set_character", name=n))
        cc.addWidget(self.combo); r1.addLayout(cc)
        ss = QVBoxLayout(); ss.addWidget(QLabel("Shape"))
        self.shape_combo = QComboBox()
        self.shape_combo.addItems(["square", "rounded", "circle"])
        self.shape_combo.setCurrentText(self.frame_state.get("shape", "rounded"))
        self.shape_combo.currentTextChanged.connect(self._on_shape)
        ss.addWidget(self.shape_combo); r1.addLayout(ss)
        lo.addLayout(r1)

        # HSL
        self._add_hsl_row(lo, "Hue", 0, 360, "hue", 200)
        self._add_hsl_row(lo, "Sat", 0, 100, "saturation", 70, fmt=lambda v: f"{v}%")
        self._add_hsl_row(lo, "Lum", 5, 95, "lightness", 45, fmt=lambda v: f"{v}%")

        lo.addWidget(self._sep())

        # Opacity + Border
        r2 = QHBoxLayout(); r2.setSpacing(8)
        self._slider_pair(r2, "BG", 5, 95, "opacity",
                          int(self.frame_state.get("opacity", 0.8) * 100),
                          fmt=lambda v: f"{v}%", cb=self._on_opacity)
        self._slider_pair(r2, "Edge", 0, 20, "border_width",
                          int(self.frame_state.get("border_width", 2.0) * 2),
                          fmt=lambda v: f"{v/2:.1f}px", cb=self._on_border)
        lo.addLayout(r2)

        # Glow + Pulse
        r3 = QHBoxLayout(); r3.setSpacing(8)
        self._slider_pair(r3, "Glow", 0, 100, "glow_intensity",
                          self.frame_state.get("glow_intensity", 50),
                          fmt=lambda v: f"{v}%", cb=self._on_glow)
        self._slider_pair(r3, "Pulse", 0, 100, "pulse_speed",
                          int(self.frame_state.get("pulse_speed", 3.0) * 10),
                          fmt=lambda v: f"{v/10:.1f}s" if v > 0 else "OFF", cb=self._on_pulse)
        lo.addLayout(r3)

        # Wave amplitude
        r3b = QHBoxLayout(); r3b.setSpacing(8)
        self._slider_pair(r3b, "Wave", 0, 100, "pulse_amplitude",
                          self.frame_state.get("pulse_amplitude", 30),
                          fmt=lambda v: f"{v}%", cb=self._on_pulse_amp)
        lo.addLayout(r3b)

        lo.addWidget(self._sep())

        # Size + Volume
        r4 = QHBoxLayout(); r4.setSpacing(8)
        parent = self.parent()
        sz = getattr(parent, '_avatar_size', 220) if parent else 220
        self._slider_pair(r4, "Size", 100, 400, "size", sz,
                          fmt=lambda v: f"{v}px", cb=self._on_size)
        self._slider_pair(r4, "Vol", 0, 100, "volume", 80, fmt=lambda v: f"{v}%",
                          cb=lambda v: (self.vol_val.setText(f"{v}%"),
                                        self._emit("set_volume", value=v / 100)))
        lo.addLayout(r4)

        # Mic sensitivity + Blink
        r5 = QHBoxLayout(); r5.setSpacing(8)
        self._slider_pair(r5, "Mic", 1, 20, "silence_seconds", 4,
                          fmt=lambda v: f"{v/10:.1f}s",
                          cb=lambda v: (self.silence_val.setText(f"{v/10:.1f}s"),
                                        self._emit("set_silence_seconds", value=v / 10)))
        self._slider_pair(r5, "Blink", 10, 100, "blink_interval", 45,
                          fmt=lambda v: f"{v/10:.1f}s",
                          cb=lambda v: (self.blink_val.setText(f"{v/10:.1f}s"),
                                        self._emit("set_blink_interval", value=v / 10)))
        lo.addLayout(r5)

        # Backend selector
        lo.addWidget(self._sep())
        be_row = QHBoxLayout(); be_row.setSpacing(6)
        be_lbl = QLabel("Agent"); be_lbl.setFixedWidth(40)
        be_row.addWidget(be_lbl)
        self.backend_combo = QComboBox()
        self.backend_combo.setMinimumWidth(160)
        for key, label, gly in SettingsPopup._backend_options:
            self.backend_combo.addItem(f"{gly}  {label}", key)
        self.backend_combo.currentIndexChanged.connect(self._on_backend)
        be_row.addWidget(self.backend_combo, stretch=1)
        self.backend_status = QLabel(); self.backend_status.setFixedWidth(20)
        be_row.addWidget(self.backend_status)
        lo.addLayout(be_row)

        # Debug waveform toggle
        lo.addWidget(self._sep())
        dbg_row = QHBoxLayout(); dbg_row.setSpacing(6)
        dbg_check = QCheckBox("\U0001f50a  Audio Waveform")
        dbg_check.setChecked(True)
        dbg_check.toggled.connect(lambda v: self._emit("debug_overlay", enabled=v))
        dbg_row.addWidget(dbg_check)
        dbg_row.addStretch()
        self._debug_check = dbg_check
        lo.addLayout(dbg_row)

        lo.addStretch()
        return tab

    # ═══════════════════════════════════════════════════════════════
    #  Tab 2: Agent (LLM / STT / TTS / Wake Word)
    # ═══════════════════════════════════════════════════════════════

    def _build_agent_tab(self) -> QWidget:
        tab = QWidget()
        lo = QVBoxLayout(tab)
        lo.setContentsMargins(0, 4, 0, 0)
        lo.setSpacing(4)

        # ── LLM ──
        gb = QGroupBox("LLM")
        f = QFormLayout(gb); f.setSpacing(3); f.setContentsMargins(8, 16, 8, 8)

        self._llm_provider = QComboBox()
        for p in ["hermes", "openai-compatible", "ollama", "odysseus"]:
            self._llm_provider.addItem(p)
        self._llm_provider.currentTextChanged.connect(
            lambda v: self._emit("config", section="llm", key="provider", value=v))
        f.addRow("Provider:", self._llm_provider)

        self._llm_model = QLineEdit("hermes-agent")
        self._llm_model.textChanged.connect(
            lambda v: self._emit("config", section="llm", key="model", value=v))
        f.addRow("Model:", self._llm_model)

        self._llm_url = QLineEdit("http://127.0.0.1:8642/v1")
        self._llm_url.textChanged.connect(
            lambda v: self._emit("config", section="llm", key="base_url", value=v))
        f.addRow("Base URL:", self._llm_url)

        self._llm_key = QLineEdit()
        self._llm_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._llm_key.setPlaceholderText("(optional)")
        self._llm_key.textChanged.connect(
            lambda v: self._emit("config", section="llm", key="api_key", value=v))
        f.addRow("API Key:", self._llm_key)
        lo.addWidget(gb)

        # ── STT ──
        gb2 = QGroupBox("STT")
        f2 = QFormLayout(gb2); f2.setSpacing(3); f2.setContentsMargins(8, 16, 8, 8)
        self._stt_provider = QComboBox()
        for p in ["faster-whisper", "parakeet"]:
            self._stt_provider.addItem(p)
        self._stt_provider.currentTextChanged.connect(
            lambda v: self._emit("config", section="stt", key="provider", value=v))
        f2.addRow("Provider:", self._stt_provider)
        self._stt_model = QComboBox()
        for m in ["tiny", "base", "small", "medium", "large-v3"]:
            self._stt_model.addItem(m)
        self._stt_model.setCurrentText("tiny")
        self._stt_model.currentTextChanged.connect(
            lambda v: self._emit("config", section="stt", key="model", value=v))
        f2.addRow("Model:", self._stt_model)
        lo.addWidget(gb2)

        # ── TTS ──
        gb3 = QGroupBox("TTS")
        f3 = QFormLayout(gb3); f3.setSpacing(3); f3.setContentsMargins(8, 16, 8, 8)
        self._tts_provider = QComboBox()
        for p in ["kokoro", "dots", "espeak-ng"]:
            self._tts_provider.addItem(p)
        self._tts_provider.currentTextChanged.connect(
            lambda v: self._emit("config", section="tts", key="provider", value=v))
        f3.addRow("Provider:", self._tts_provider)
        self._tts_voice = QLineEdit("af_heart")
        self._tts_voice.textChanged.connect(
            lambda v: self._emit("config", section="tts", key="voice", value=v))
        f3.addRow("Voice:", self._tts_voice)
        lo.addWidget(gb3)

        # ── Wake Word ──
        gb4 = QGroupBox("Wake Word")
        f4 = QFormLayout(gb4); f4.setSpacing(3); f4.setContentsMargins(8, 16, 8, 8)
        self._wake_phrase = QLineEdit("hey rhasspy")
        self._wake_phrase.textChanged.connect(
            lambda v: self._emit("config", section="assistant", key="wake_phrase", value=v))
        f4.addRow("Phrase:", self._wake_phrase)
        lo.addWidget(gb4)

        lo.addStretch()
        return tab

    # ═══════════════════════════════════════════════════════════════
    #  Tab 3: Cloud (LiveKit / LemonSlice / Gemini)
    # ═══════════════════════════════════════════════════════════════

    def _build_cloud_tab(self) -> QWidget:
        tab = QWidget()
        lo = QVBoxLayout(tab)
        lo.setContentsMargins(0, 4, 0, 0)
        lo.setSpacing(4)

        # ── LiveKit ──
        gb = QGroupBox("LiveKit")
        f = QFormLayout(gb); f.setSpacing(3); f.setContentsMargins(8, 16, 8, 8)
        self._lk_url = QLineEdit("ws://127.0.0.1:7880")
        self._lk_url.textChanged.connect(
            lambda v: self._emit("config", section="livekit", key="url", value=v))
        f.addRow("URL:", self._lk_url)
        self._lk_key = QLineEdit("devkey")
        self._lk_key.textChanged.connect(
            lambda v: self._emit("config", section="livekit", key="api_key", value=v))
        f.addRow("API Key:", self._lk_key)
        self._lk_secret = QLineEdit("secret")
        self._lk_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self._lk_secret.textChanged.connect(
            lambda v: self._emit("config", section="livekit", key="api_secret", value=v))
        f.addRow("Secret:", self._lk_secret)
        lo.addWidget(gb)

        # ── LemonSlice ──
        gb2 = QGroupBox("LemonSlice (Video Avatar)")
        f2 = QFormLayout(gb2); f2.setSpacing(3); f2.setContentsMargins(8, 16, 8, 8)
        self._ls_key = QLineEdit()
        self._ls_key.setPlaceholderText("Get key at lemonslice.com")
        self._ls_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._ls_key.textChanged.connect(
            lambda v: self._emit("config", section="lemonslice", key="api_key", value=v))
        f2.addRow("API Key:", self._ls_key)
        self._ls_img = QLineEdit()
        self._ls_img.setPlaceholderText("Public HTTP(S) URL of avatar photo")
        self._ls_img.textChanged.connect(
            lambda v: self._emit("config", section="lemonslice", key="image_url", value=v))
        f2.addRow("Image URL:", self._ls_img)
        lo.addWidget(gb2)

        # ── Gemini ──
        gb3 = QGroupBox("Gemini")
        f3 = QFormLayout(gb3); f3.setSpacing(3); f3.setContentsMargins(8, 16, 8, 8)
        self._gm_key = QLineEdit()
        self._gm_key.setPlaceholderText("GOOGLE_API_KEY")
        self._gm_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._gm_key.textChanged.connect(
            lambda v: self._emit("config", section="gemini", key="api_key", value=v))
        f3.addRow("API Key:", self._gm_key)
        self._gm_model = QComboBox()
        for m in ["gemini-2.5-flash-native-audio-preview-12-2025",
                   "gemini-3.1-flash-live-preview"]:
            self._gm_model.addItem(m)
        self._gm_model.currentTextChanged.connect(
            lambda v: self._emit("config", section="gemini", key="model", value=v))
        f3.addRow("Model:", self._gm_model)
        self._gm_voice = QComboBox()
        for v in ["Puck", "Charon", "Kore", "Fenrir", "Aoede"]:
            self._gm_voice.addItem(v)
        self._gm_voice.currentTextChanged.connect(
            lambda v: self._emit("config", section="gemini", key="voice", value=v))
        f3.addRow("Voice:", self._gm_voice)
        lo.addWidget(gb3)

        lo.addStretch()
        return tab

    # ═══════════════════════════════════════════════════════════════
    #  Tab 4: Profiles / Presets
    # ═══════════════════════════════════════════════════════════════

    def _build_profiles_tab(self) -> QWidget:
        tab = QWidget()
        lo = QVBoxLayout(tab)
        lo.setContentsMargins(0, 4, 0, 0)
        lo.setSpacing(6)

        lo.addWidget(QLabel("Save/load full config snapshots:"))

        self._profile_list = QComboBox()
        self._profile_list.setMinimumWidth(200)
        self._refresh_profiles()
        lo.addWidget(self._profile_list)

        br = QHBoxLayout(); br.setSpacing(4)
        load_btn = QPushButton("Load"); load_btn.clicked.connect(self._load_profile); br.addWidget(load_btn)
        save_btn = QPushButton("Save"); save_btn.clicked.connect(self._save_profile); br.addWidget(save_btn)
        saveas_btn = QPushButton("Save As\u2026"); saveas_btn.clicked.connect(self._save_as_profile); br.addWidget(saveas_btn)
        del_btn = QPushButton("Del"); del_btn.clicked.connect(self._del_profile); br.addWidget(del_btn)
        lo.addLayout(br)

        lo.addStretch()
        return tab

    # ── Profile helpers ──────────────────────────────────────────

    def _refresh_profiles(self) -> None:
        self._profile_list.clear()
        self._profile_list.addItem("\u2014 select \u2014")
        try:
            for f in sorted(PROFILES_DIR.glob("*.yaml")):
                self._profile_list.addItem(f.stem)
        except OSError:
            pass

    def _gather_config(self) -> dict[str, Any]:
        """Collect ALL current settings into one config dict for saving."""
        return {
            "display": dict(self.frame_state),
            "llm": {
                "provider": self._llm_provider.currentText(),
                "model": self._llm_model.text(),
                "base_url": self._llm_url.text(),
                "api_key": self._llm_key.text(),
            },
            "stt": {
                "provider": self._stt_provider.currentText(),
                "model": self._stt_model.currentText(),
            },
            "tts": {
                "provider": self._tts_provider.currentText(),
                "voice": self._tts_voice.text(),
            },
            "assistant": {"wake_phrase": self._wake_phrase.text()},
            "livekit": {
                "url": self._lk_url.text(),
                "api_key": self._lk_key.text(),
                "api_secret": self._lk_secret.text(),
            },
            "lemonslice": {
                "api_key": self._ls_key.text(),
                "image_url": self._ls_img.text(),
            },
            "gemini": {
                "api_key": self._gm_key.text(),
                "model": self._gm_model.currentText(),
                "voice": self._gm_voice.currentText(),
            },
        }

    def _apply_config(self, cfg: dict[str, Any]) -> None:
        """Apply a saved config to all UI widgets + emit settings."""
        if "display" in cfg:
            d = cfg["display"]
            for k, v in d.items():
                if k in self.frame_state:
                    self.frame_state[k] = v
                s = getattr(self, f"{k}_slider", None)
                if s is not None:
                    try:
                        s.setValue(int(v))
                    except (ValueError, TypeError):
                        pass
            self._emit("set_frame_style", **self.frame_state)

        # Sections: emit each as full-section config update
        sections = ["llm", "stt", "tts", "assistant", "livekit", "lemonslice", "gemini"]
        for sec in sections:
            if sec not in cfg:
                continue
            data = cfg[sec]
            # Update UI widgets if they exist
            if sec == "llm":
                if "provider" in data:
                    i = self._llm_provider.findText(data["provider"])
                    if i >= 0: self._llm_provider.setCurrentIndex(i)
                if "model" in data: self._llm_model.setText(data["model"])
                if "base_url" in data: self._llm_url.setText(data["base_url"])
                if "api_key" in data: self._llm_key.setText(data["api_key"])
            elif sec == "stt":
                if "provider" in data:
                    i = self._stt_provider.findText(data["provider"])
                    if i >= 0: self._stt_provider.setCurrentIndex(i)
                if "model" in data:
                    i = self._stt_model.findText(data["model"])
                    if i >= 0: self._stt_model.setCurrentIndex(i)
            elif sec == "tts":
                if "provider" in data:
                    i = self._tts_provider.findText(data["provider"])
                    if i >= 0: self._tts_provider.setCurrentIndex(i)
                if "voice" in data: self._tts_voice.setText(data["voice"])
            elif sec == "assistant":
                if "wake_phrase" in data: self._wake_phrase.setText(data["wake_phrase"])
            elif sec == "livekit":
                if "url" in data: self._lk_url.setText(data["url"])
                if "api_key" in data: self._lk_key.setText(data["api_key"])
                if "api_secret" in data: self._lk_secret.setText(data["api_secret"])
            elif sec == "lemonslice":
                if "api_key" in data: self._ls_key.setText(data["api_key"])
                if "image_url" in data: self._ls_img.setText(data["image_url"])
            elif sec == "gemini":
                if "api_key" in data: self._gm_key.setText(data["api_key"])
                if "model" in data:
                    i = self._gm_model.findText(data["model"])
                    if i >= 0: self._gm_model.setCurrentIndex(i)
                if "voice" in data:
                    i = self._gm_voice.findText(data["voice"])
                    if i >= 0: self._gm_voice.setCurrentIndex(i)
            self._emit("config", section=sec, key="*", value=data)
        self._emit("config_reload")  # Signal assistant to reload everything

    def _load_profile(self) -> None:
        name = self._profile_list.currentText()
        if not name or name == "\u2014 select \u2014":
            return
        path = PROFILES_DIR / f"{name}.yaml"
        if not path.exists():
            return
        try:
            import yaml
            cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            self._apply_config(cfg)
        except Exception as e:
            print(f"[profile] load error: {e}", flush=True)

    def _save_profile(self) -> None:
        name = self._profile_list.currentText()
        if not name or name == "\u2014 select \u2014":
            self._save_as_profile()
            return
        self._do_save(name)

    def _save_as_profile(self) -> None:
        name, ok = QInputDialog.getText(self, "Save Preset", "Preset name:")
        if ok and name.strip():
            self._do_save(name.strip())
            self._refresh_profiles()
            i = self._profile_list.findText(name.strip())
            if i >= 0: self._profile_list.setCurrentIndex(i)

    def _do_save(self, name: str) -> None:
        path = PROFILES_DIR / f"{name}.yaml"
        try:
            import yaml
            cfg = self._gather_config()
            path.write_text(yaml.dump(cfg, default_flow_style=False, sort_keys=False))
            self._refresh_profiles()
            i = self._profile_list.findText(name)
            if i >= 0: self._profile_list.setCurrentIndex(i)
        except Exception as e:
            print(f"[profile] save error: {e}", flush=True)

    def _del_profile(self) -> None:
        name = self._profile_list.currentText()
        if not name or name == "\u2014 select \u2014":
            return
        path = PROFILES_DIR / f"{name}.yaml"
        if path.exists():
            path.unlink()
            self._refresh_profiles()

    # ═══════════════════════════════════════════════════════════════
    #  Helpers
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _sep() -> QFrame:
        s = QFrame()
        s.setFrameShape(QFrame.Shape.HLine)
        s.setStyleSheet("color: rgba(100,180,255,0.08);")
        return s

    def _add_hsl_row(self, parent: QVBoxLayout, label: str,
                     lo: int, hi: int, key: str, default: int,
                     fmt=lambda v: str(v)) -> None:
        row = QHBoxLayout(); row.setSpacing(4)
        lbl = QLabel(label); lbl.setFixedWidth(26)
        row.addWidget(lbl)
        sl = QSlider(Qt.Orientation.Horizontal)
        sl.setRange(lo, hi)
        sl.setValue(self.frame_state.get(key, default))
        vl = QLabel(fmt(sl.value()))
        sl.valueChanged.connect(
            lambda v, k=key, vl=vl, f=fmt: (
                vl.setText(f(v)), self.frame_state.__setitem__(k, v),
                self._emit("set_frame_style", **self.frame_state)))
        row.addWidget(sl, stretch=1); row.addWidget(vl)
        setattr(self, f"{key}_slider", sl)
        setattr(self, f"{key}_val", vl)
        parent.addLayout(row)

    def _slider_pair(self, parent: QHBoxLayout, label: str,
                     lo: int, hi: int, key: str, default: int,
                     fmt=lambda v: str(v), cb=None) -> None:
        col = QVBoxLayout(); col.setSpacing(1)
        row = QHBoxLayout(); row.setSpacing(3)
        lbl = QLabel(label); row.addWidget(lbl)
        sl = QSlider(Qt.Orientation.Horizontal)
        sl.setRange(lo, hi); sl.setValue(default)
        vl = QLabel(fmt(default))
        if cb:
            sl.valueChanged.connect(lambda v, vl=vl, f=fmt, c=cb: (vl.setText(f(v)), c(v)))
        else:
            sl.valueChanged.connect(
                lambda v, k=key, vl=vl, f=fmt: (
                    vl.setText(f(v)), self.frame_state.__setitem__(k, v),
                    self._emit("set_frame_style", **self.frame_state)))
        row.addWidget(sl, stretch=1); row.addWidget(vl)
        col.addLayout(row)
        setattr(self, f"{key}_slider", sl)
        setattr(self, f"{key}_val", vl)
        parent.addLayout(col)

    # ═══════════════════════════════════════════════════════════════
    #  Event handlers
    # ═══════════════════════════════════════════════════════════════

    def _emit(self, cmd: str, **kw: Any) -> None:
        payload = {"cmd": cmd, **kw}
        self.setting_changed.emit(payload)
        print(json.dumps(payload), flush=True)

    def _on_shape(self, shape: str) -> None:
        self.frame_state["shape"] = shape
        self._emit("set_frame_style", **self.frame_state)

    def _on_backend(self, idx: int) -> None:
        key = self.backend_combo.itemData(idx)
        if not key:
            return
        self.backend_status.setText("\u2713")
        self.backend_status.setStyleSheet("color: #4c4;")
        self._emit("set_backend", provider=key)

    def _on_opacity(self, val: int) -> None:
        self.frame_state["opacity"] = val / 100
        self._emit("set_frame_style", **self.frame_state)

    def _on_border(self, val: int) -> None:
        self.frame_state["border_width"] = val / 2
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

    def sync_frame_state(self, state: dict[str, Any]) -> None:
        """Sync display tab sliders from external frame state update."""
        self.frame_state.update(state)
        for key, s_attr, v_attr, fmt in [
            ("hue", "hue_slider", "hue_val", str),
            ("saturation", "saturation_slider", "saturation_val", lambda v: f"{v}%"),
            ("lightness", "lightness_slider", "lightness_val", lambda v: f"{v}%"),
            ("opacity", "opacity_slider", "opacity_val", lambda v: f"{v}%"),
            ("border_width", "border_width_slider", "border_width_val", lambda v: f"{v/2:.1f}px"),
            ("glow_intensity", "glow_intensity_slider", "glow_intensity_val", lambda v: f"{v}%"),
            ("pulse_speed", "pulse_speed_slider", "pulse_speed_val",
             lambda v: f"{v/10:.1f}s" if v > 0 else "OFF"),
            ("pulse_amplitude", "pulse_amplitude_slider", "pulse_amplitude_val", lambda v: f"{v}%"),
        ]:
            if key not in state:
                continue
            sl = getattr(self, s_attr, None) if s_attr else None
            v = state[key]
            if key == "border_width": v = int(state["border_width"] * 2)
            elif key == "opacity": v = int(state["opacity"] * 100)
            elif key == "pulse_speed": v = int(state["pulse_speed"] * 10)
            if sl:
                sl.blockSignals(True); sl.setValue(v); sl.blockSignals(False)
            if v_attr:
                lbl = getattr(self, v_attr, None)
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
            px = max(8, x - self.width())
            py = max(8, y - self.height())
        screen = QGuiApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            px = max(geo.x() + 4, px)
            if px + self.width() > geo.right():
                px = geo.right() - self.width() - 4
            py = max(geo.y() + 4, min(py, geo.bottom() - self.height() - 4))
        self.move(px, py)
        self.show()

    # ── Class-level backend options API ──────────────────────────

    @staticmethod
    def set_backend_options(options: list[tuple[str, str, str]]) -> None:
        SettingsPopup._backend_options = options
        if options:
            SettingsPopup._backend_default = options[0][0]
