#!/usr/bin/env python3
"""Echo-Node Incarnation Chooser — unified launcher with settings.

A PyQt6 window that shows all 3 voice agent incarnations as cards.
Switch between them, tweak settings, start/stop — all from one place.

Usage:
  echo-node                   # GUI mode (launches Qt window)
  echo-node --list            # list incarnations
  echo-node --start 0         # start incarnation 0 headless
  echo-node --stop            # stop current
  echo-node --status          # check running state
"""

from __future__ import annotations

import json
import logging
import os
import platform
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

try:
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QPalette, QColor
    from PyQt6.QtWidgets import (
        QApplication, QCheckBox, QComboBox, QFrame, QHBoxLayout,
        QLabel, QLineEdit, QMainWindow, QPushButton,
        QSlider, QDoubleSpinBox, QVBoxLayout, QWidget, QGroupBox,
        QFormLayout, QMessageBox,
    )
    _HAS_GUI = True
except ImportError:
    _HAS_GUI = False

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("chooser")

# ── Paths ─────────────────────────────────────────────────────────

_REPO = Path(__file__).resolve().parent.parent
_CONFIG = _REPO / "incarnations.yaml"
_ENV_FILE = _REPO / ".env"

SYSTEM = platform.system().lower()
IS_LINUX = SYSTEM == "linux"
IS_MACOS = SYSTEM == "darwin"
IS_WSL = "microsoft" in platform.uname().release.lower() if IS_LINUX else False


# ═══════════════════════════════════════════════════════════════════
#  Backend: configuration data + subprocess management
# ═══════════════════════════════════════════════════════════════════


@dataclass
class SettingDef:
    """Definition for a single configurable setting."""
    key: str
    label: str
    type: str  # text, password, number, range, dropdown, boolean
    default: Any = ""
    options: list[str] | None = None
    min: float | None = None
    max: float | None = None
    step: float | None = None
    description: str = ""

    def coerce(self, value: Any) -> Any:
        if self.type == "number":
            return float(value)
        elif self.type == "boolean":
            if isinstance(value, bool):
                return value
            return str(value).lower() in ("true", "1", "yes")
        elif self.type == "range":
            return float(value)
        return str(value)


@dataclass
class Incarnation:
    """A complete incarnation definition."""
    name: str
    description: str
    command: dict[str, str]
    cwd: str = "."
    log_file: str = "logs/incarnation.log"
    settings: dict[str, SettingDef] = field(default_factory=dict)
    values: dict[str, Any] = field(default_factory=dict)

    def get_command(self) -> str:
        if IS_WSL:
            tmpl = self.command.get("wsl") or self.command.get("linux", "")
        elif IS_MACOS:
            tmpl = self.command.get("macos") or self.command.get("linux", "")
        else:
            tmpl = self.command.get("linux", "")
        cwd_abs = str((_REPO / self.cwd).resolve())
        return tmpl.replace("${CWD}", cwd_abs)

    def get_env(self) -> dict[str, str]:
        env = os.environ.copy()
        for key, val in self.values.items():
            env[key.upper().replace(".", "_")] = str(val)
        return env

    def get_value(self, key: str) -> Any:
        if key in self.values:
            return self.values[key]
        sd = self.settings.get(key)
        return sd.default if sd else ""


class IncarnationManager:
    """Loads/saves config, manages subprocess lifecycle."""

    def __init__(self, config_path: Path = _CONFIG):
        self.config_path = config_path
        self.incarnations: list[Incarnation] = []
        self.active_index: int = -1
        self._process: subprocess.Popen | None = None
        self._proc_start: float = 0.0
        self.load()

    def load(self) -> None:
        if not self.config_path.exists():
            log.warning(f"Config not found: {self.config_path}")
            return
        with open(self.config_path) as f:
            data = yaml.safe_load(f)
        self.active_index = data.get("active", -1)
        self.incarnations = []
        for raw in data.get("incarnations", []):
            inc = Incarnation(
                name=raw["name"],
                description=raw.get("description", ""),
                command=raw.get("command", {"linux": "", "macos": "", "wsl": ""}),
                cwd=raw.get("cwd", "."),
                log_file=raw.get("log_file", "logs/incarnation.log"),
            )
            for s_key, s_data in raw.get("settings", {}).items():
                sd = SettingDef(
                    key=s_key,
                    label=s_data.get("label", s_key),
                    type=s_data.get("type", "text"),
                    default=s_data.get("default", ""),
                    options=s_data.get("options"),
                    min=s_data.get("min"),
                    max=s_data.get("max"),
                    step=s_data.get("step"),
                    description=s_data.get("description", ""),
                )
                inc.settings[s_key] = sd
                inc.values[s_key] = sd.default
            saved = raw.get("values", {})
            for k, v in saved.items():
                if k in inc.settings:
                    inc.values[k] = inc.settings[k].coerce(v)
            self.incarnations.append(inc)
        log.info(f"Loaded {len(self.incarnations)} incarnations")

    def save(self) -> None:
        data = {"active": self.active_index, "incarnations": []}
        for inc in self.incarnations:
            raw = {
                "name": inc.name, "description": inc.description,
                "command": inc.command, "cwd": inc.cwd,
                "log_file": inc.log_file, "settings": {}, "values": inc.values,
            }
            for s_key, sd in inc.settings.items():
                entry = {"label": sd.label, "type": sd.type,
                         "default": sd.default, "description": sd.description}
                if sd.options: entry["options"] = sd.options
                if sd.min is not None: entry["min"] = sd.min
                if sd.max is not None: entry["max"] = sd.max
                if sd.step is not None: entry["step"] = sd.step
                raw["settings"][s_key] = entry
            data["incarnations"].append(raw)
        self.config_path.write_text(
            "# Echo-Node Incarnation Configuration\n"
            + yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
        )

    def update_value(self, inc_idx: int, key: str, value: Any) -> None:
        if 0 <= inc_idx < len(self.incarnations):
            inc = self.incarnations[inc_idx]
            if key in inc.settings:
                inc.values[key] = inc.settings[key].coerce(value)

    def is_running(self) -> bool:
        if self._process is None:
            return False
        return self._process.poll() is None

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self._proc_start if self._process and self.is_running() else 0.0

    def switch_to(self, inc_idx: int) -> str | None:
        self.stop()
        time.sleep(0.5)
        if inc_idx < 0 or inc_idx >= len(self.incarnations):
            self.active_index = -1
            self.save()
            return None
        inc = self.incarnations[inc_idx]
        cmd = inc.get_command()
        if not cmd:
            return f"No command for platform {SYSTEM}"
        env = inc.get_env()
        cwd_abs = str((_REPO / inc.cwd).resolve())
        log_path = _REPO / inc.log_file
        log_path.parent.mkdir(exist_ok=True)
        try:
            log.info(f"Starting: {inc.name}")
            self._process = subprocess.Popen(
                cmd, shell=True, cwd=cwd_abs, env=env,
                stdout=open(log_path, "a"), stderr=subprocess.STDOUT,
                preexec_fn=(os.setpgrp if not IS_WSL else None),
            )
            self._proc_start = time.time()
            self.active_index = inc_idx
            self.save()
            self._write_env_file(inc_idx)
            return None
        except Exception as e:
            self._process = None
            self.active_index = -1
            return str(e)

    def stop(self) -> None:
        if self._process is None:
            return
        log.info(f"Stopping (PID={self._process.pid})...")
        try:
            if not IS_WSL:
                os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
            else:
                self._process.terminate()
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                if not IS_WSL:
                    os.killpg(os.getpgid(self._process.pid), signal.SIGKILL)
                else:
                    self._process.kill()
            except (ProcessLookupError, PermissionError):
                pass
        except (ProcessLookupError, PermissionError):
            pass
        self._process = None
        self._proc_start = 0.0
        self.active_index = -1
        self.save()

    def _write_env_file(self, inc_idx: int) -> None:
        inc = self.incarnations[inc_idx]
        with open(_ENV_FILE, "w") as f:
            f.write(f"# Echo-Node active incarnation: {inc.name}\n")
            f.write(f"ECHO_NODE_INCARNATION={inc_idx}\n")
            for key, val in inc.values.items():
                f.write(f'{key.upper().replace(".", "_")}="{val}"\n')
            if self._process:
                f.write(f'ECHO_NODE_PID="{self._process.pid}"\n')


_manager: IncarnationManager | None = None


def get_manager() -> IncarnationManager:
    global _manager
    if _manager is None:
        _manager = IncarnationManager()
    return _manager


# ═══════════════════════════════════════════════════════════════════
#  CLI interface
# ═══════════════════════════════════════════════════════════════════

def _cli_main():
    mgr = get_manager()
    if "--list" in sys.argv:
        for i, inc in enumerate(mgr.incarnations):
            r = "▶ RUNNING" if i == mgr.active_index and mgr.is_running() else ""
            print(f"  [{i}] {inc.name} {r}")
            print(f"       {inc.description}")
        return
    if "--start" in sys.argv:
        idx = int(sys.argv[sys.argv.index("--start") + 1])
        err = mgr.switch_to(idx)
        if err:
            print(f"ERROR: {err}", file=sys.stderr)
            sys.exit(1)
        print(f"Started: {mgr.incarnations[idx].name}")
        return
    if "--stop" in sys.argv:
        mgr.stop()
        print("Stopped.")
        return
    if "--status" in sys.argv:
        if mgr.active_index >= 0 and mgr.is_running():
            inc = mgr.incarnations[mgr.active_index]
            print(f"▶ {inc.name} (PID={mgr._process.pid}, uptime={mgr.uptime_seconds:.0f}s)")
        else:
            print("⏹  No incarnation running")
        return
    _launch_gui()


# ═══════════════════════════════════════════════════════════════════
#  GUI — launched only when PyQt6 is available
# ═══════════════════════════════════════════════════════════════════

def _launch_gui():
    if not _HAS_GUI:
        print("ERROR: PyQt6 required for GUI mode. Install:", file=sys.stderr)
        print("  pip install PyQt6", file=sys.stderr)
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setApplicationName("Echo-Node Chooser")
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#1a1a2e"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#e0e0ff"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#16213e"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#0f3460"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#e0e0ff"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#533483"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)

    win = _ChooserWindow(get_manager())
    win.show()
    sys.exit(app.exec())


class _ChooserWindow(QMainWindow):
    STYLE = """
        QMainWindow { background: #1a1a2e; }
        QLabel { color: #e0e0ff; }
        QComboBox, QLineEdit, QDoubleSpinBox {
            background: #16213e; color: #e0e0ff; border: 1px solid #533483;
            border-radius: 4px; padding: 4px 8px; min-height: 24px;
        }
        QComboBox::drop-down { border: none; }
        QComboBox QAbstractItemView {
            background: #16213e; color: #e0e0ff; selection-bg: #533483;
        }
        QPushButton {
            background: #0f3460; color: #e0e0ff; border: 1px solid #533483;
            border-radius: 6px; padding: 8px 20px; font-weight: bold;
        }
        QPushButton:hover { background: #1a4a80; }
        QPushButton:disabled { background: #2a2a3e; color: #666; }
        QGroupBox {
            font-weight: bold; border: 1px solid #533483; border-radius: 8px;
            margin-top: 12px; padding: 16px 12px 12px;
        }
        QGroupBox::title {
            subcontrol-origin: margin; padding: 0 8px; color: #e0e0ff;
        }
        QCheckBox { color: #e0e0ff; spacing: 8px; }
        QSlider::groove:horizontal { height: 6px; background: #16213e; border-radius: 3px; }
        QSlider::handle:horizontal { background: #533483; width: 16px; border-radius: 8px; }
        QSlider::sub-page:horizontal { background: #7c4dff; border-radius: 3px; }
    """

    def __init__(self, mgr):
        super().__init__()
        self.mgr = mgr
        self._cards: list[_IncarnationCard] = []
        self._status_label = QLabel()
        self._init_ui()
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.start(2000)

    def _init_ui(self):
        self.setWindowTitle("Echo-Node Incarnation Chooser")
        self.setMinimumSize(900, 700)
        self.setStyleSheet(self.STYLE)

        c = QWidget()
        self.setCentralWidget(c)
        lo = QVBoxLayout(c)
        lo.setContentsMargins(20, 20, 20, 20)
        lo.setSpacing(16)

        h = QLabel("🎛️  Echo-Node Incarnation Selector")
        h.setStyleSheet("font-size: 24px; font-weight: bold; color: #e0e0ff;")
        lo.addWidget(h)
        s = QLabel("Choose your voice agent pipeline — each has different trade-offs.")
        s.setStyleSheet("font-size: 13px; color: #8888aa;")
        lo.addWidget(s)

        cards_lo = QHBoxLayout()
        cards_lo.setSpacing(16)
        for i, inc in enumerate(self.mgr.incarnations):
            card = _IncarnationCard(i, inc, self)
            self._cards.append(card)
            cards_lo.addWidget(card)
        lo.addLayout(cards_lo)

        btn_lo = QHBoxLayout()
        btn_lo.setSpacing(12)
        stop_btn = QPushButton("⏹  Stop All")
        stop_btn.clicked.connect(lambda: (self.mgr.stop(), self._tick()))
        stop_btn.setMinimumHeight(40)
        btn_lo.addWidget(stop_btn)
        btn_lo.addStretch()
        save_btn = QPushButton("💾  Save All Settings")
        save_btn.clicked.connect(self._save_all)
        save_btn.setMinimumHeight(40)
        btn_lo.addWidget(save_btn)
        lo.addLayout(btn_lo)

        self._status_label.setStyleSheet("color: #6666aa; font-size: 12px; padding: 4px 0;")
        lo.addWidget(self._status_label)
        self._tick()

    def _tick(self):
        if self.mgr.is_running():
            inc = self.mgr.incarnations[self.mgr.active_index]
            self._status_label.setText(
                f"▶ Running: {inc.name}  |  PID: {self.mgr._process.pid}  |  "
                f"Uptime: {self.mgr.uptime_seconds:.0f}s")
            self._status_label.setStyleSheet("color: #4caf50; font-size: 12px; padding: 4px 0;")
        else:
            self._status_label.setText("⏹  Idle — no incarnation running")
            self._status_label.setStyleSheet("color: #6666aa; font-size: 12px;")
        for card in self._cards:
            card._refresh()

    def _save_all(self):
        for card in self._cards:
            card._pull()
        self.mgr.save()
        self._status_label.setText("💾 Saved!")
        self._status_label.setStyleSheet("color: #7c4dff; font-size: 12px;")


class _IncarnationCard(QFrame):
    def __init__(self, index: int, inc: Incarnation, parent: _ChooserWindow):
        super().__init__()
        self._index = index
        self._inc = inc
        self._win = parent
        self._mgr = parent.mgr
        self._expanded = False
        self._widgets: dict[str, QWidget] = {}
        self._init_ui()

    def _init_ui(self):
        self.setObjectName("card")
        self.setMinimumWidth(280)
        self.setMaximumWidth(380)

        lo = QVBoxLayout(self)
        lo.setContentsMargins(16, 16, 16, 16)
        lo.setSpacing(8)

        name = QLabel(self._inc.name)
        name.setStyleSheet("font-size: 18px; font-weight: bold; color: #e0e0ff;")
        name.setWordWrap(True)
        lo.addWidget(name)

        desc = QLabel(self._inc.description)
        desc.setStyleSheet("font-size: 12px; color: #8888aa;")
        desc.setWordWrap(True)
        lo.addWidget(desc)

        self._status = QLabel("⏹  Idle")
        self._status.setStyleSheet("font-size: 12px; color: #6666aa;")
        lo.addWidget(self._status)

        self._btn = QPushButton("▶  Launch")
        self._btn.setMinimumHeight(44)
        self._btn.setStyleSheet("QPushButton { font-size: 14px; font-weight: bold; }")
        self._btn.clicked.connect(self._toggle)
        lo.addWidget(self._btn)

        expand = QPushButton("⚙  Settings  ▼")
        expand.setMinimumHeight(32)
        expand.setStyleSheet("QPushButton { font-size: 12px; background: transparent; border: 1px solid #533483; } QPushButton:hover { background: #1a2440; }")
        expand.clicked.connect(self._toggle_expand)
        lo.addWidget(expand)

        self._settings_w = QWidget()
        self._settings_w.setVisible(False)
        slo = QVBoxLayout(self._settings_w)
        slo.setContentsMargins(0, 8, 0, 0)
        slo.setSpacing(4)

        groups: dict[str, list[tuple[str, SettingDef]]] = {}
        for s_key, sd in self._inc.settings.items():
            cat = s_key.split(".")[0] if "." in s_key else "general"
            groups.setdefault(cat, []).append((s_key, sd))

        for cat in sorted(groups.keys()):
            gb = QGroupBox(cat.capitalize())
            form = QFormLayout(gb)
            form.setSpacing(6)
            form.setContentsMargins(8, 16, 8, 8)
            for s_key, sd in groups[cat]:
                w = self._make_widget(s_key, sd)
                if w:
                    self._widgets[s_key] = w
                    form.addRow(QLabel(sd.label), w)
            slo.addWidget(gb)

        lo.addWidget(self._settings_w)
        lo.addStretch()
        self._refresh()

    def _make_widget(self, s_key: str, sd: SettingDef) -> QWidget | None:
        cur = self._inc.get_value(s_key)
        if sd.type == "dropdown":
            cb = QComboBox()
            cb.addItems(sd.options or [])
            i = cb.findText(str(cur))
            if i >= 0: cb.setCurrentIndex(i)
            cb.currentTextChanged.connect(lambda v, k=s_key: self._mgr.update_value(self._index, k, v))
            return cb
        elif sd.type == "boolean":
            cb = QCheckBox()
            cb.setChecked(bool(cur) if not isinstance(cur, str) else cur.lower() == "true")
            cb.toggled.connect(lambda v, k=s_key: self._mgr.update_value(self._index, k, v))
            return cb
        elif sd.type == "password":
            le = QLineEdit(str(cur))
            le.setEchoMode(QLineEdit.EchoMode.Password)
            le.textChanged.connect(lambda v, k=s_key: self._mgr.update_value(self._index, k, v))
            return le
        elif sd.type == "number":
            sb = QDoubleSpinBox()
            sb.setRange(sd.min or 0, sd.max or 9999)
            sb.setValue(float(cur))
            sb.valueChanged.connect(lambda v, k=s_key: self._mgr.update_value(self._index, k, v))
            return sb
        elif sd.type == "range":
            container = QWidget()
            hl = QHBoxLayout(container)
            hl.setContentsMargins(0, 0, 0, 0)
            sl = QSlider(Qt.Orientation.Horizontal)
            n_steps = int((sd.max or 100) / (sd.step or 1))
            sl.setMinimum(0)
            sl.setMaximum(n_steps)
            sl.setValue(int(float(cur) / (sd.step or 1)))
            vl = QLabel(str(cur))
            vl.setStyleSheet("color: #aaa; font-size: 11px; min-width: 40px;")
            hl.addWidget(sl)
            hl.addWidget(vl)
            def _slider(v, k=s_key, lbl=vl, sd=sd):
                r = v * (sd.step or 1)
                lbl.setText(f"{r:.2f}")
                self._mgr.update_value(self._index, k, r)
            sl.valueChanged.connect(_slider)
            return container
        else:
            le = QLineEdit(str(cur))
            le.textChanged.connect(lambda v, k=s_key: self._mgr.update_value(self._index, k, v))
            return le

    def _pull(self):
        """Read UI values back into manager (not needed if we update on change)."""
        pass

    def _toggle(self):
        if self._mgr.active_index == self._index and self._mgr.is_running():
            self._mgr.stop()
        else:
            err = self._mgr.switch_to(self._index)
            if err:
                QMessageBox.warning(self, "Error", f"Failed to start:\n{err}")
        self._win._tick()

    def _toggle_expand(self):
        self._expanded = not self._expanded
        self._settings_w.setVisible(self._expanded)
        btn = self.layout().itemAt(5).widget()  # the expand button
        if btn:
            btn.setText("⚙  Settings  ▲" if self._expanded else "⚙  Settings  ▼")

    def _refresh(self):
        is_active = self._mgr.active_index == self._index
        is_running = self._mgr.is_running()
        if is_active and is_running:
            self._status.setText(f"▶  Running (PID: {self._mgr._process.pid})")
            self._status.setStyleSheet("font-size: 12px; color: #4caf50;")
            self._btn.setText("⏹  Stop")
            self._btn.setStyleSheet("QPushButton { font-size: 14px; font-weight: bold; background: #b71c1c; } QPushButton:hover { background: #d32f2f; }")
            self.setStyleSheet("QFrame#card { background: #16213e; border: 2px solid #4caf50; border-radius: 12px; }")
        else:
            self._status.setText("⏹  Idle")
            self._status.setStyleSheet("font-size: 12px; color: #6666aa;")
            self._btn.setText("▶  Launch")
            self._btn.setStyleSheet("QPushButton { font-size: 14px; font-weight: bold; background: #0f3460; } QPushButton:hover { background: #1a4a80; }")
            self.setStyleSheet("QFrame#card { background: #16213e; border: 1px solid #2a2a4e; border-radius: 12px; }")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        _cli_main()
    else:
        _launch_gui()
