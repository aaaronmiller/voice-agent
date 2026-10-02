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
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
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


def _registry_provider_names(slot_name: str, fallback: list[str]) -> list[tuple[str, str, bool | None, str, str]]:
    """Dropdown options from the slot registry: validated providers only.

    Returns ``(config_key, display_label, valid, reason, cap_summary)`` tuples;
    external (subprocess) providers get an " (external)" suffix on the label so users
    can tell them apart from built-ins. ``valid``/``reason`` come from the
    cached ``last_validation`` (populated by ``working()`` below, falling
    back to a live ``validate()`` when nothing is cached) so the UI can
    show ✓/✗ marks with the reason as tooltip. ``cap_summary`` is the
    one-line Capability summary (streaming/batch, languages, CPU/GPU) shown
    under the reason in the tooltip. ``valid`` is None for the
    hardcoded fallback entries, which carry no validation info.

    NOTE: this popup runs in the avatar sidecar process, which has its own
    registry instance — validation results here reflect *this* process
    (same as the existing dropdown population, which already validated
    here). External providers are mirrored into the sidecar registry from
    config.yaml by ``SettingsPopup._sync_external_registry`` at popup
    construction.
    """
    try:
        from echo_node.slots import SlotType
        from echo_node.slots.registry import get_registry
        from echo_node.adapters.ui_helpers import format_capability_summary
        slot = SlotType(slot_name)
        reg = get_registry()
        infos = reg.working(slot)
        pairs = []
        for i in infos:
            res = i.last_validation or i.validate()
            pairs.append((i.name, i.name + (" (external)" if i.external else ""),
                          res.ok, res.reason,
                          format_capability_summary(getattr(i, "capabilities", None))))
        return pairs or [(n, n, None, "", "") for n in fallback]
    except Exception:
        return [(n, n, None, "", "") for n in fallback]


def _valid_mark(valid: bool | None) -> str:
    """✓/✗ prefix for dropdown labels ("" when validation is unknown)."""
    if valid is True:
        return "\u2713 "
    if valid is False:
        return "\u2717 "
    return ""


# (slot, name) pairs this sidecar process registered from config.yaml's
# external_providers:. Tracked so each new popup can unregister the stale
# set before re-registering the current file contents.
_EXTERNAL_SYNCED: list[tuple[Any, str]] = []


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
                 current_char: str, frame_state: dict[str, Any],
                 config_path: str | None = None):
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

        # Config path (sidecar argv --config): source of truth for the
        # External tab. The sidecar registry is synced from it below so the
        # Agent/Display dropdowns see external providers too.
        self._config_path = config_path
        self._ext_sync_error: str | None = self._sync_external_registry()
        SettingsPopup._backend_options = self._registry_backend_options()

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
        self._external_tab = self._build_external_tab()
        self.tabs.addTab(self._external_tab, "External")
        self.tabs.addTab(self._build_profiles_tab(), "Presets")
        self.tabs.currentChanged.connect(self._on_tab_changed)

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
        self._populate_backend_combo()
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
        self._stt_provider.currentIndexChanged.connect(
            lambda _i: self._emit("config", section="stt", key="provider",
                                 value=self._stt_provider.currentData()))
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
        self._tts_provider.currentIndexChanged.connect(
            lambda _i: self._emit("config", section="tts", key="provider",
                                 value=self._tts_provider.currentData()))
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

        # Populate the registry-driven dropdowns (after all combos exist)
        self._populate_provider_combos()

        # ── Validation ──
        vr = QHBoxLayout(); vr.setSpacing(6)
        recheck_btn = QPushButton("Re-check providers")
        recheck_btn.clicked.connect(self._recheck_providers)
        vr.addWidget(recheck_btn)
        self._agent_recheck_status = QLabel("")
        self._agent_recheck_status.setWordWrap(True)
        vr.addWidget(self._agent_recheck_status, stretch=1)
        lo.addLayout(vr)

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

    # ═══════════════════════════════════════════════════════════════
    #  Tab: External providers (config.yaml external_providers:)
    # ═══════════════════════════════════════════════════════════════

    def _on_tab_changed(self, idx: int) -> None:
        if self.tabs.widget(idx) is getattr(self, "_external_tab", None):
            self._refresh_external_list()

    def _sync_external_registry(self) -> str | None:
        """Mirror config.yaml's ``external_providers:`` into this process's registry.

        The popup (and its Agent/Display dropdowns) runs in the avatar
        sidecar process, which has its own registry instance — the
        assistant's live registry is a different object. Re-registering
        here keeps the sidecar's dropdowns and validation dots honest.
        Returns an error string, or None on success. Never raises.
        """
        global _EXTERNAL_SYNCED
        try:
            from echo_node.slots.registry import get_registry
            reg = get_registry()
        except Exception as exc:
            return f"registry unavailable: {exc}"
        for slot, name in _EXTERNAL_SYNCED:
            try:
                reg.unregister(slot, name)
            except Exception:
                pass
        _EXTERNAL_SYNCED = []
        if not self._config_path:
            return None  # sidecar started without --config: nothing to mirror
        entries, err = self._load_external_entries()
        if err:
            return err
        try:
            from echo_node.adapters import (
                ExternalProviderError,
                register_external_providers,
            )
            from echo_node.slots import SlotType
            names = register_external_providers(
                {"external_providers": entries}, reg)
        except ExternalProviderError as exc:
            return str(exc)
        except Exception as exc:
            return f"registry sync failed: {exc}"
        for dotted in names:
            s, _, n = dotted.partition("/")
            try:
                _EXTERNAL_SYNCED.append((SlotType(s), n))
            except ValueError:
                pass
        return None

    def _load_external_entries(self) -> tuple[list[dict[str, Any]], str | None]:
        """Read config.yaml's ``external_providers:`` — (entries, error).

        The config file is the source of truth; this never raises.
        """
        if not self._config_path:
            return [], "no config path (sidecar started without --config)"
        try:
            import yaml
            cfg = yaml.safe_load(
                Path(self._config_path).read_text(encoding="utf-8")) or {}
        except Exception as exc:
            return [], f"cannot read config.yaml: {exc}"
        entries = cfg.get("external_providers") or []
        if not isinstance(entries, list):
            return [], "'external_providers' must be a list"
        return [e for e in entries if isinstance(e, dict)], None

    @staticmethod
    def _registry_backend_options() -> list[tuple[str, str, str]]:
        """Rebuild backend (key, label, glyph) options from the sidecar registry.

        Same population rule as ``echo_node.backends._build_backend_options``
        (validated, non-experimental, " (external)" suffix for externals),
        run after ``_sync_external_registry`` so external backends appear.
        Glyphs are preserved from the previously-set options where known.
        """
        previous = list(SettingsPopup._backend_options)
        try:
            from echo_node.slots import SlotType
            from echo_node.slots.registry import get_registry
            reg = get_registry()
            working = reg.working(SlotType.AGENT_BACKEND)
            if not working:
                working = [i for i in reg.all_providers(SlotType.AGENT_BACKEND)
                           if not i.experimental]
            glyphs = {k: g for k, _l, g in previous}
            out = []
            for i in working:
                label = getattr(i.provider_cls, "name", None) or i.name
                if i.external:
                    label += " (external)"
                out.append((i.name, label, glyphs.get(i.name, "")))
            return out or previous
        except Exception:
            return previous

    def _provider_tooltip(self, reason: str, cap_summary: str) -> str:
        """Combine the validation reason and capability summary for a
        dropdown tooltip (capability line first — it's the stable fact,
        the reason is the transient state)."""
        reason = (reason or "").strip()
        cap_summary = (cap_summary or "").strip()
        if cap_summary and reason:
            return cap_summary + "\n" + reason
        return cap_summary or reason

    def _populate_provider_combos(self) -> None:
        """(Re)build the STT/TTS dropdowns from the registry, keeping selection."""
        for combo, slot_name, fallback in (
            (self._stt_provider, "stt", ["faster-whisper", "parakeet"]),
            (self._tts_provider, "tts", ["kokoro", "dots", "espeak-ng"]),
        ):
            current = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            for key, label, valid, reason, cap_summary in _registry_provider_names(slot_name, fallback):
                combo.addItem(_valid_mark(valid) + label, key)
                tooltip = self._provider_tooltip(reason, cap_summary)
                if tooltip:
                    combo.setItemData(combo.count() - 1, tooltip,
                                      Qt.ItemDataRole.ToolTipRole)
            if current is not None:
                idx = combo.findData(current)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            combo.blockSignals(False)

    def _populate_backend_combo(self) -> None:
        """(Re)build the Display-tab backend combo with ✓/✗ validation marks."""
        current = self.backend_combo.currentData()
        try:
            from echo_node.slots import SlotType
            from echo_node.slots.registry import get_registry
            from echo_node.adapters.ui_helpers import format_capability_summary
            reg = get_registry()
            marks: dict[str, tuple[bool | None, str, str]] = {}
            for i in reg.all_providers(SlotType.AGENT_BACKEND):
                res = i.last_validation or i.validate()
                marks[i.name] = (res.ok, res.reason,
                                 format_capability_summary(getattr(i, "capabilities", None)))
        except Exception:
            marks = {}
        self.backend_combo.blockSignals(True)
        self.backend_combo.clear()
        for key, label, gly in SettingsPopup._backend_options:
            valid, reason, cap_summary = marks.get(key, (None, "", ""))
            self.backend_combo.addItem(f"{_valid_mark(valid)}{gly}  {label}", key)
            tooltip = self._provider_tooltip(reason, cap_summary)
            if tooltip:
                self.backend_combo.setItemData(self.backend_combo.count() - 1, tooltip,
                                              Qt.ItemDataRole.ToolTipRole)
        if current is not None:
            idx = self.backend_combo.findData(current)
            if idx >= 0:
                self.backend_combo.setCurrentIndex(idx)
        self.backend_combo.blockSignals(False)

    def _recheck_providers(self) -> None:
        """Re-run all validators and rebuild the provider dropdowns."""
        try:
            from echo_node.slots.registry import get_registry
            get_registry().refresh()
            self._populate_provider_combos()
            self._populate_backend_combo()
            self._agent_recheck_status.setText("re-checked just now")
            self._agent_recheck_status.setStyleSheet("color: #4c4;")
        except Exception as exc:
            self._agent_recheck_status.setText(f"re-check failed: {exc}")
            self._agent_recheck_status.setStyleSheet("color: #c44;")

    def _build_external_tab(self) -> QWidget:
        tab = QWidget()
        lo = QVBoxLayout(tab)
        lo.setContentsMargins(0, 4, 0, 0)
        lo.setSpacing(4)

        trust = QLabel(
            "External programs run with your user privileges \u2014 "
            "only add software you trust.")
        trust.setWordWrap(True)
        lo.addWidget(trust)

        self._ext_list = QListWidget()
        self._ext_list.itemDoubleClicked.connect(lambda _i: self._on_ext_edit())
        lo.addWidget(self._ext_list, stretch=1)

        self._ext_status = QLabel("")
        self._ext_status.setWordWrap(True)
        lo.addWidget(self._ext_status)

        br = QHBoxLayout(); br.setSpacing(4)
        add_btn = QPushButton("Add"); add_btn.clicked.connect(self._on_ext_add)
        edit_btn = QPushButton("Edit"); edit_btn.clicked.connect(self._on_ext_edit)
        del_btn = QPushButton("Remove"); del_btn.clicked.connect(self._on_ext_remove)
        test_btn = QPushButton("Test"); test_btn.clicked.connect(self._on_ext_test)
        recheck_btn = QPushButton("Re-check all")
        recheck_btn.clicked.connect(self._on_ext_recheck)
        for b in (add_btn, edit_btn, del_btn, test_btn, recheck_btn):
            br.addWidget(b)
        lo.addLayout(br)

        lo.addStretch()
        self._refresh_external_list()
        return tab

    def _set_ext_status(self, text: str, ok: bool | None) -> None:
        self._ext_status.setText(text)
        color = "#4c4" if ok else ("#c44" if ok is False else "#aab")
        self._ext_status.setStyleSheet(f"color: {color};")

    @staticmethod
    def _entry_argv_summary(e: dict[str, Any]) -> str:
        from echo_node.adapters.ui_helpers import summarize_command
        try:
            from echo_node.adapters import resolve_command
            argv = resolve_command(e.get("command") or [], e.get("args") or [],
                                   name=str(e.get("name", "?")))
        except Exception:
            argv = ([str(c) for c in (e.get("command") or [])]
                    + [str(a) for a in (e.get("args") or [])])
        return summarize_command(argv)

    def _external_status(self, slot: str, name: str) -> tuple[bool | None, str]:
        """(ok, reason) for one entry, from this process's registry."""
        try:
            from echo_node.slots import SlotType
            from echo_node.slots.registry import get_registry
            info = get_registry().info(SlotType(slot), name)
        except Exception as exc:
            return None, f"not in this process's registry: {exc}"
        try:
            res = info.last_validation or info.validate()
            return res.ok, res.reason
        except Exception as exc:
            return False, f"validator crashed: {exc}"

    def _refresh_external_list(self) -> None:
        self._ext_list.clear()
        entries, err = self._load_external_entries()
        if err:
            self._set_ext_status(err, ok=False)
            return
        if self._ext_sync_error:
            self._set_ext_status(f"registry sync: {self._ext_sync_error}", ok=False)
        else:
            self._set_ext_status(
                f"{len(entries)} external provider(s) in config.yaml", ok=True)
        for e in entries:
            name = str(e.get("name", "?"))
            slot = str(e.get("slot", "?"))
            ok, reason = self._external_status(slot, name)
            color = "#4c4" if ok else ("#c44" if ok is False else "#889")
            item = QListWidgetItem(
                f"\u25cf  {name}  [{slot}]  \u2014  {self._entry_argv_summary(e)}")
            item.setForeground(QColor(color))
            item.setToolTip(reason or "no validation info yet")
            item.setData(Qt.ItemDataRole.UserRole, e)
            self._ext_list.addItem(item)

    def _selected_external_entry(self) -> dict[str, Any] | None:
        item = self._ext_list.currentItem()
        if item is None:
            return None
        e = item.data(Qt.ItemDataRole.UserRole)
        return e if isinstance(e, dict) else None

    def _on_ext_add(self) -> None:
        dlg = ExternalProviderDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            entry = dlg.get_entry()
            self._set_ext_status(f"saving {entry['name']}\u2026", ok=None)
            self._emit("external_provider_save", entry=entry)

    def _on_ext_edit(self) -> None:
        e = self._selected_external_entry()
        if e is None:
            return
        dlg = ExternalProviderDialog(self, entry=e)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            entry = dlg.get_entry()
            self._set_ext_status(f"saving {entry['name']}\u2026", ok=None)
            self._emit("external_provider_save", entry=entry)

    def _on_ext_remove(self) -> None:
        e = self._selected_external_entry()
        if e is None:
            return
        name, slot = str(e.get("name", "?")), str(e.get("slot", "?"))
        ans = QMessageBox.question(
            self, "Remove external provider",
            f"Remove external provider {name!r} [{slot}]?\n\n"
            "This deletes it from config.yaml's external_providers: and "
            "unregisters it immediately.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if ans == QMessageBox.StandardButton.Yes:
            self._set_ext_status(f"removing {name}\u2026", ok=None)
            self._emit("external_provider_remove", slot=slot, name=name)

    def _on_ext_test(self) -> None:
        e = self._selected_external_entry()
        if e is None:
            return
        name, slot = str(e.get("name", "?")), str(e.get("slot", "?"))
        try:
            from echo_node.slots import SlotType
            from echo_node.slots.registry import get_registry
            info = get_registry().info(SlotType(slot), name)
            info.last_validation = None
            res = info.validate()
            self._set_ext_status(
                f"{name}: {'\u2713' if res.ok else '\u2717'} {res.reason}", ok=res.ok)
        except Exception as exc:
            self._set_ext_status(f"{name}: test failed: {exc}", ok=False)
        self._refresh_external_list()

    def _on_ext_recheck(self) -> None:
        try:
            from echo_node.slots.registry import get_registry
            reg = get_registry()
            for slot, name in _EXTERNAL_SYNCED:
                reg.refresh(slot, name)
            self._set_ext_status("re-checked all external providers", ok=True)
        except Exception as exc:
            self._set_ext_status(f"re-check failed: {exc}", ok=False)
        self._refresh_external_list()

    def _on_external_result(self, payload: dict[str, Any]) -> None:
        """Handle the assistant's reply to external_provider_save/remove.

        Called by avatar.window.CommandRouter when the assistant sends
        ``{"cmd": "external_provider_result", ...}`` back over stdin.
        """
        ok = bool(payload.get("ok", False))
        message = str(payload.get("message", ""))
        # Re-mirror config.yaml into this process's registry, then refresh
        # every surface that shows providers.
        self._ext_sync_error = self._sync_external_registry()
        self._refresh_external_list()
        self._populate_provider_combos()
        self._populate_backend_combo()
        self._set_ext_status(message, ok=ok)
        if not ok:
            QMessageBox.warning(self, "External provider", message)

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
                "provider": self._stt_provider.currentData() or self._stt_provider.currentText(),
                "model": self._stt_model.currentText(),
            },
            "tts": {
                "provider": self._tts_provider.currentData() or self._tts_provider.currentText(),
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
                    i = self._stt_provider.findData(data["provider"])
                    if i < 0:
                        i = self._stt_provider.findText(data["provider"])
                    if i >= 0: self._stt_provider.setCurrentIndex(i)
                if "model" in data:
                    i = self._stt_model.findText(data["model"])
                    if i >= 0: self._stt_model.setCurrentIndex(i)
            elif sec == "tts":
                if "provider" in data:
                    i = self._tts_provider.findData(data["provider"])
                    if i < 0:
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


# ── External provider Add/Edit dialog ─────────────────────────────

class ExternalProviderDialog(QDialog):
    """Add/Edit dialog for one config.yaml ``external_providers:`` entry.

    The entry dict is built with the Qt-free
    ``echo_node.adapters.ui_helpers`` (same schema ``_validate_entry``
    accepts). The Test button runs the exact validation the registry
    would — ``make_external_provider`` + ``validate()`` — before anything
    is saved. Saving itself is the popup's job: it emits
    ``external_provider_save`` and the assistant persists to config.yaml.
    """

    def __init__(self, parent: QWidget, entry: dict[str, Any] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Edit external provider" if entry else "Add external provider")
        self.setMinimumWidth(440)

        lo = QVBoxLayout(self)
        lo.setSpacing(4)
        f = QFormLayout(); f.setSpacing(4)

        # Slot — only slots the subprocess protocol supports
        self.slot_combo = QComboBox()
        try:
            from echo_node.adapters.subprocess_adapter import SUPPORTED_SLOTS
            for s in sorted(s.value for s in SUPPORTED_SLOTS):
                self.slot_combo.addItem(s)
        except Exception:
            for s in ["stt", "tts", "vad", "wake_word", "agent_backend"]:
                self.slot_combo.addItem(s)
        f.addRow("Slot:", self.slot_combo)

        # Name + inline validation
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. whispercpp")
        self.name_edit.textChanged.connect(self._check_name)
        self.name_error = QLabel("")
        self.name_error.setStyleSheet("color: #c44;")
        f.addRow("Name:", self.name_edit)
        f.addRow("", self.name_error)

        # Repo adapter quick-pick
        self.builtin_combo = QComboBox()
        self.builtin_combo.addItem("Custom command\u2026", None)
        try:
            from echo_node.adapters import BUILTIN_ADAPTERS
            for b in sorted(BUILTIN_ADAPTERS):
                self.builtin_combo.addItem(f"repo: {b}", f"builtin:{b}")
        except Exception:
            pass
        self.builtin_combo.currentIndexChanged.connect(self._on_builtin_pick)
        f.addRow("Adapter:", self.builtin_combo)

        # Command argv, one element per line
        self.command_edit = QPlainTextEdit()
        self.command_edit.setFixedHeight(72)
        self.command_edit.setPlaceholderText(
            "Command argv, one element per line:\n"
            "builtin:stt_whispercpp.py\nor\n"
            "/usr/local/bin/my-stt\n--model\n/path/to/model.bin")
        f.addRow("Command:", self.command_edit)

        # Extra args, one per line
        self.args_edit = QPlainTextEdit()
        self.args_edit.setFixedHeight(48)
        self.args_edit.setPlaceholderText("Extra args, one per line (optional)")
        f.addRow("Args:", self.args_edit)
        lo.addLayout(f)

        # Numeric options
        nr = QHBoxLayout(); nr.setSpacing(8)
        self.proto_spin = QSpinBox(); self.proto_spin.setRange(1, 99)
        self.proto_spin.setValue(1); self.proto_spin.setPrefix("v")
        nr.addWidget(QLabel("Protocol:")); nr.addWidget(self.proto_spin)
        self.req_spin = QSpinBox(); self.req_spin.setRange(1, 3600)
        self.req_spin.setValue(30); self.req_spin.setSuffix(" s")
        nr.addWidget(QLabel("Request timeout:")); nr.addWidget(self.req_spin)
        lo.addLayout(nr)

        nr2 = QHBoxLayout(); nr2.setSpacing(8)
        self.idle_spin = QSpinBox(); self.idle_spin.setRange(5, 86400)
        self.idle_spin.setValue(120); self.idle_spin.setSuffix(" s")
        nr2.addWidget(QLabel("Idle timeout:")); nr2.addWidget(self.idle_spin)
        self.restart_spin = QSpinBox(); self.restart_spin.setRange(0, 100)
        self.restart_spin.setValue(3)
        nr2.addWidget(QLabel("Max restarts:")); nr2.addWidget(self.restart_spin)
        nr2.addStretch()
        lo.addLayout(nr2)

        self.experimental_check = QCheckBox(
            "Experimental (hidden from dropdowns unless ECHO_INCLUDE_EXPERIMENTAL=1)")
        lo.addWidget(self.experimental_check)

        # Test row
        test_row = QHBoxLayout(); test_row.setSpacing(6)
        test_btn = QPushButton("Test")
        test_btn.clicked.connect(self._on_test)
        test_row.addWidget(test_btn)
        self._test_result = QLabel("")
        self._test_result.setWordWrap(True)
        test_row.addWidget(self._test_result, stretch=1)
        lo.addLayout(test_row)

        bbox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bbox.accepted.connect(self._on_accept)
        bbox.rejected.connect(self.reject)
        lo.addWidget(bbox)

        if entry:
            self._prefill(entry)

    # ── internals ──────────────────────────────────────────────

    def _prefill(self, entry: dict[str, Any]) -> None:
        from echo_node.adapters.ui_helpers import format_args_text
        i = self.slot_combo.findText(str(entry.get("slot", "")))
        if i >= 0:
            self.slot_combo.setCurrentIndex(i)
        self.name_edit.setText(str(entry.get("name", "")))
        self.command_edit.setPlainText(format_args_text(entry.get("command") or []))
        self.args_edit.setPlainText(format_args_text(entry.get("args") or []))
        cmd0 = (entry.get("command") or [None])[0]
        if isinstance(cmd0, str) and cmd0.startswith("builtin:"):
            i = self.builtin_combo.findData(cmd0)
            if i >= 0:
                self.builtin_combo.setCurrentIndex(i)
        try:
            self.proto_spin.setValue(int(entry.get("protocol_version", 1)))
            self.req_spin.setValue(int(float(entry.get("request_timeout_s", 30))))
            self.idle_spin.setValue(int(float(entry.get("idle_timeout_s", 120))))
            self.restart_spin.setValue(int(entry.get("max_restarts", 3)))
        except (TypeError, ValueError):
            pass
        self.experimental_check.setChecked(bool(entry.get("experimental", False)))

    def _check_name(self, text: str) -> None:
        from echo_node.adapters.ui_helpers import validate_name
        err = validate_name(text.strip())
        self.name_error.setText(err or "")

    def _on_builtin_pick(self, idx: int) -> None:
        builtin = self.builtin_combo.itemData(idx)
        if builtin:
            self.command_edit.setPlainText(builtin)

    def _on_accept(self) -> None:
        from echo_node.adapters.ui_helpers import parse_args_text, validate_name
        name = self.name_edit.text().strip()
        err = validate_name(name)
        if err:
            self.name_error.setText(err)
            return
        if not parse_args_text(self.command_edit.toPlainText()):
            self.name_error.setText("command must be a non-empty argv list")
            return
        self.accept()

    def _on_test(self) -> None:
        from PyQt6.QtWidgets import QApplication
        self._test_result.setText("testing\u2026")
        self._test_result.setStyleSheet("color: #aab;")
        QApplication.processEvents()
        try:
            from echo_node.adapters import _validate_entry
            from echo_node.adapters.subprocess_adapter import make_external_provider
            norm = _validate_entry(self.get_entry(), 0)
            cls = make_external_provider(norm)
            res = cls.validate()
        except Exception as exc:
            self._test_result.setText(f"\u2717 {exc}")
            self._test_result.setStyleSheet("color: #c44;")
            return
        mark = "\u2713" if res.ok else "\u2717"
        self._test_result.setText(f"{mark} {res.reason}")
        self._test_result.setStyleSheet(
            f"color: {'#4c4' if res.ok else '#c44'};")
        self._test_result.setToolTip(res.reason)

    def get_entry(self) -> dict[str, Any]:
        """Build the config-shaped entry dict from the dialog fields."""
        from echo_node.adapters.ui_helpers import build_entry_dict, parse_args_text
        return build_entry_dict(
            slot=self.slot_combo.currentText(),
            name=self.name_edit.text().strip(),
            command=parse_args_text(self.command_edit.toPlainText()),
            args=parse_args_text(self.args_edit.toPlainText()),
            protocol_version=self.proto_spin.value(),
            request_timeout_s=float(self.req_spin.value()),
            idle_timeout_s=float(self.idle_spin.value()),
            max_restarts=self.restart_spin.value(),
            experimental=self.experimental_check.isChecked(),
        )
