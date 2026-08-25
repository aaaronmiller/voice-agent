#!/usr/bin/env python3
"""
BabelFish Configurator — Textual TUI for profile management.

Standalone app that lists profiles, shows/edits settings, and launches/sto ps.
Runs independently of the voice assistant (no circular dependency).

Usage:
  babelfish-config          # launch the TUI
  babelfish-config --list   # list profiles and exit
"""

from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import Any

# Ensure we can import sibling modules
_REPO = Path(__file__).resolve().parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from profiles import ProfileManager, profile_manager, Profile


try:
    from textual import work
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical, ScrollableContainer
    from textual.screen import ModalScreen, Screen
    from textual.reactive import reactive
    from textual.widgets import (
        Button, Footer, Header, Input, Label, ListItem,
        ListView, RichLog, Static, TextArea, Select,
    )
    from textual.widget import Widget
except ImportError as e:
    print(f"ERROR: Textual required but not installed: {e}", file=sys.stderr)
    print("  pip install textual", file=sys.stderr)
    sys.exit(1)


# ── Shared Styles ────────────────────────────────────────────────────

DARK_CSS = """
Screen {
    background: #0d1117;
}

#app-layout {
    layout: horizontal;
    height: 100%;
}

#profile-list-panel {
    width: 34%;
    min-width: 30;
    max-width: 45;
    height: 100%;
    border-right: solid #30363d;
    background: #161b22;
    padding: 0 1;
}

#profile-list-panel > Label {
    color: #8b949e;
    text-style: bold;
    padding: 1 0;
}

ListView {
    height: 1fr;
    border: none;
    background: transparent;
}

ListView > ListItem {
    padding: 1 1;
    background: transparent;
    color: #c9d1d9;
}

ListView > ListItem.--highlight {
    background: #1f6feb33;
    color: #58a6ff;
}

ListView > ListItem > Label {
    padding: 0;
}

#running-badge {
    color: #3fb950;
    text-style: bold;
}

#profile-detail-panel {
    width: 66%;
    height: 100%;
    background: #0d1117;
    padding: 1 2;
}

#detail-header {
    color: #c9d1d9;
    text-style: bold;
    padding: 1 0;
    border-bottom: solid #30363d;
    margin-bottom: 1;
}

.SettingRow {
    layout: horizontal;
    height: 3;
    margin: 0 0 1 0;
}

.SettingRow > Label {
    width: 30;
    padding: 1 0;
    color: #8b949e;
}

.SettingRow > Input {
    width: 1fr;
}

.SettingRow > Select {
    width: 1fr;
}

Select {
    background: #21262d;
    color: #c9d1d9;
    border: solid #30363d;
}

Select > .select-value {
    color: #c9d1d9;
}

Select > .select-icon {
    color: #8b949e;
}

Select > .select-dropdown {
    background: #21262d;
    border: solid #30363d;
}

Select > .select-dropdown > .select-item {
    color: #c9d1d9;
}

Select > .select-dropdown > .select-item:hover {
    background: #1f6feb33;
}

Select:focus {
    border: solid #58a6ff;
}

Input {
    background: #21262d;
    color: #c9d1d9;
    border: solid #30363d;
    padding: 0 1;
}

Input:focus {
    border: solid #58a6ff;
}

Input.-invalid {
    border: solid #da3633;
}

#action-bar {
    layout: horizontal;
    height: 3;
    margin: 1 0;
    padding: 0;
}

#action-bar > Button {
    margin: 0 1 0 0;
    min-width: 12;
}

Button {
    background: #21262d;
    color: #c9d1d9;
    border: solid #30363d;
    padding: 0 2;
}

Button:hover {
    background: #30363d;
}

Button:focus {
    border: solid #58a6ff;
}

Button.primary {
    background: #238636;
    color: #ffffff;
    border: solid #238636;
}

Button.primary:hover {
    background: #2ea043;
}

Button.danger {
    background: #da3633;
    color: #ffffff;
    border: solid #da3633;
}

Button.danger:hover {
    background: #f85149;
}

#status-bar {
    height: 1;
    color: #8b949e;
}

#running-status {
    color: #3fb950;
}

#idle-status {
    color: #8b949e;
}

#empty-state {
    align: center middle;
    color: #8b949e;
    text-style: italic;
}

#empty-state > Static {
    padding: 1;
}

#template-label {
    color: #58a6ff;
    padding: 0 0 1 0;
}

#desc-area {
    background: #21262d;
    color: #c9d1d9;
    border: solid #30363d;
    height: 3;
}
"""


# ═════════════════════════════════════════════════════════════════════
#  Profile List Item
# ═════════════════════════════════════════════════════════════════════

class ProfileItem(Widget):
    """A single profile entry in the list."""

    def __init__(self, profile: Profile, running: bool = False) -> None:
        super().__init__()
        self._profile = profile
        self._running = running

    def compose(self) -> ComposeResult:
        name = self._profile.name
        if self._running:
            yield Label(f"▶ {name}", id="running-badge")
        else:
            yield Label(name)

    def on_mount(self) -> None:
        self.styles.padding = (1, 1)


# ═════════════════════════════════════════════════════════════════════
#  Create Profile Modal
# ═════════════════════════════════════════════════════════════════════

class CreateProfileScreen(ModalScreen[dict | None]):
    """Modal dialog for creating a new profile."""

    CSS = """
    #create-dialog {
        width: 50;
        height: auto;
        background: #161b22;
        border: solid #30363d;
        padding: 2 3;
        margin: 4 8;
    }
    #create-dialog > Label {
        color: #c9d1d9;
        padding: 1 0;
    }
    #create-dialog > Input {
        width: 100%;
    }
    #create-buttons {
        layout: horizontal;
        height: 3;
        margin-top: 1;
    }
    #create-buttons > Button {
        margin: 0 1 0 0;
    }
    Select {
        width: 100%;
        background: #21262d;
        color: #c9d1d9;
        border: solid #30363d;
    }
    """

    def compose(self) -> ComposeResult:
        pm = profile_manager()
        with Vertical(id="create-dialog"):
            yield Label("Create New Profile")
            yield Label("Name:")
            yield Input(placeholder="Profile name", id="create-name")
            yield Label("Template:")
            options = []
            for i, inc in enumerate(pm._template_mgr.incarnations):
                options.append((f"[{i}] {inc.name}", str(i)))
            yield Select(options, value="0", id="create-template")
            yield Label("Description:")
            yield Input(placeholder="Optional description", id="create-desc")
            with Horizontal(id="create-buttons"):
                yield Button("Create", variant="primary", id="create-confirm")
                yield Button("Cancel", id="create-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "create-cancel":
            self.dismiss(None)
        elif event.button.id == "create-confirm":
            name = self.query_one("#create-name", Input).value.strip()
            if not name:
                return
            tmpl_str = str(self.query_one("#create-template", Select).value)
            template = int(tmpl_str) if tmpl_str and tmpl_str != "SELECT" else 0
            desc = self.query_one("#create-desc", Input).value.strip()
            self.dismiss({"name": name, "template": template, "desc": desc})


# ═════════════════════════════════════════════════════════════════════
#  Delete Confirmation Modal
# ═════════════════════════════════════════════════════════════════════

class ConfirmDeleteScreen(ModalScreen[bool]):
    CSS = """
    #confirm-dialog {
        width: 40;
        height: auto;
        background: #161b22;
        border: solid #30363d;
        padding: 2 3;
        margin: 8 12;
    }
    #confirm-buttons {
        layout: horizontal;
        height: 3;
        margin-top: 1;
    }
    #confirm-buttons > Button {
        margin: 0 1 0 0;
    }
    """

    def __init__(self, profile_name: str) -> None:
        super().__init__()
        self._name = profile_name

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Label(f"Delete profile {self._name!r}?")
            yield Label("This cannot be undone.", id="sub")
            with Horizontal(id="confirm-buttons"):
                yield Button("Delete", variant="danger", id="confirm-yes")
                yield Button("Cancel", id="confirm-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-yes")


# ═════════════════════════════════════════════════════════════════════
#  Main Configurator App
# ═════════════════════════════════════════════════════════════════════

class ConfiguratorApp(App):
    """BabelFish Profile Configurator TUI."""

    CSS = DARK_CSS

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("c", "create_profile", "Create", show=True),
        Binding("d", "delete_profile", "Delete", show=True),
        Binding("l", "launch_profile", "Launch", show=True),
        Binding("escape", "focus_list", "List", show=False),
    ]

    TITLE = "🐟 BabelFish Configurator"

    def __init__(self) -> None:
        super().__init__()
        self.pm = profile_manager()
        self._selected_profile: str | None = None
        self._settings_widgets: dict[str, Widget] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="app-layout"):
            with Vertical(id="profile-list-panel"):
                yield Label("Profiles")
                yield ListView(id="profile-list")
            with Vertical(id="profile-detail-panel"):
                yield Static("", id="detail-header")
                yield Label("", id="template-label")
                yield ScrollableContainer(id="settings-scroll")
                with Horizontal(id="action-bar"):
                    yield Button("▶ Launch", id="btn-launch", variant="primary")
                    yield Button("● Stop", id="btn-stop")
                    yield Button("＋ Create", id="btn-create")
                    yield Button("✕ Delete", id="btn-delete", classes="danger")
                yield Label("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_list()
        self.set_interval(2, self._tick_status)

    # ── Profile list ─────────────────────────────────────────────────

    def _refresh_list(self) -> None:
        list_view = self.query_one("#profile-list", ListView)
        list_view.clear()
        for p in self.pm.profiles:
            running = (p.name == self.pm.active and self.pm.is_running())
            item = ListItem(ProfileItem(p, running))
            list_view.append(item)

    def _on_list_view_selected(self, event: ListView.Selected) -> None:
        """User clicked a profile in the list."""
        if event.item:
            label = event.item.query_one(Label)
            name = label.renderable or ""
            name = name.lstrip("▶ ")
            self._selected_profile = name
            self._show_profile(name)

    def _show_profile(self, name: str) -> None:
        p = self.pm.get(name)
        if not p:
            return

        # Header
        running = (name == self.pm.active and self.pm.is_running())
        status = " ▶ RUNNING" if running else ""
        self.query_one("#detail-header", Static).update(f"{p.name}{status}")

        # Template info
        tmpl_name = "(unknown)"
        if 0 <= p.template < len(self.pm._template_mgr.incarnations):
            tmpl_name = self.pm._template_mgr.incarnations[p.template].name
        self.query_one("#template-label", Label).update(f"Template: #{p.template} {tmpl_name}")

        # Settings
        scroll = self.query_one("#settings-scroll", ScrollableContainer)
        scroll.remove_children()
        self._settings_widgets.clear()

        tmpl = self.pm._template_mgr.incarnations[p.template] if p.template < len(self.pm._template_mgr.incarnations) else None
        if not tmpl:
            scroll.mount(Static("(template unavailable)", id="empty-state"))
            return

        # Gather all settings: template defaults + profile overrides
        all_settings: list[tuple[str, str, Any]] = []
        for s_key, sd in tmpl.settings.items():
            val = p.settings.get(s_key, sd.default)
            all_settings.append((s_key, sd.label, sd.type, sd.options or [], sd.min, sd.max, sd.step, val))

        # Description
        with scroll:
            yield Label("Description:")
            yield Input(value=p.description, id="desc-input", placeholder="Profile description")

        for s_key, label, stype, options, smin, smax, sstep, val in all_settings:
            row = Widget(classes="SettingRow")
            row._key = s_key
            row._stype = stype
            row._smin = smin
            row._smax = smax
            row._sstep = sstep
            row._options = options

            lbl = Label(label)
            row._label_w = lbl

            if stype == "dropdown":
                sel = Select(
                    [(o, o) for o in options],
                    value=str(val),
                    prompt="",
                )
                sel._key = s_key
                row._input_w = sel
            elif stype == "boolean":
                sel = Select(
                    [("True", "true"), ("False", "false")],
                    value="true" if str(val).lower() in ("true", "1", "yes") else "false",
                    prompt="",
                )
                sel._key = s_key
                row._input_w = sel
            elif stype == "number" or stype == "range":
                inp = Input(value=str(val), placeholder=str(smin or 0))
                inp._key = s_key
                row._input_w = inp
            elif stype == "password":
                inp = Input(value=str(val), password=True, placeholder="••••••••")
                inp._key = s_key
                row._input_w = inp
            else:
                inp = Input(value=str(val), placeholder=label)
                inp._key = s_key
                row._input_w = inp

            row.mount(lbl)
            row.mount(row._input_w)
            scroll.mount(row)
            self._settings_widgets[s_key] = row._input_w

    # ── Status bar tick ──────────────────────────────────────────────

    def _tick_status(self) -> None:
        status = self.query_one("#status-bar", Label)
        if self.pm.is_running():
            status.update(f"● Running: {self.pm.active} (PID={self.pm._process.pid}, uptime={self.pm.uptime_seconds:.0f}s)")
            status.styles.color = "#3fb950"
        else:
            status.update("○ Idle — no profile running")
            status.styles.color = "#8b949e"
        self._refresh_list()

    # ── Actions ──────────────────────────────────────────────────────

    def action_refresh(self) -> None:
        self.pm.load()
        self._refresh_list()
        if self._selected_profile and self.pm.get(self._selected_profile):
            self._show_profile(self._selected_profile)

    def action_create_profile(self) -> None:
        self.push_screen(CreateProfileScreen())

    def action_delete_profile(self) -> None:
        if not self._selected_profile:
            return
        self.push_screen(ConfirmDeleteScreen(self._selected_profile))

    def action_launch_profile(self) -> None:
        if not self._selected_profile:
            return
        self._save_current_settings()
        err = self.pm.launch(self._selected_profile)
        if err:
            self.query_one("#status-bar", Label).update(f"ERROR: {err}")
            self.query_one("#status-bar", Label).styles.color = "#da3633"
        else:
            self._refresh_list()
            self._show_profile(self._selected_profile)

    def action_focus_list(self) -> None:
        self.query_one("#profile-list", ListView).focus()

    def _save_current_settings(self) -> None:
        if not self._selected_profile:
            return
        p = self.pm.get(self._selected_profile)
        if not p:
            return

        # Description
        desc_input = self.query_one("#desc-input", Input)
        if desc_input and desc_input.value.strip():
            p.description = desc_input.value.strip()

        # Settings
        for s_key, widget in self._settings_widgets.items():
            if isinstance(widget, Select):
                val = str(widget.value)
                if val and val != "SELECT":
                    p.settings[s_key] = val
            elif isinstance(widget, Input):
                p.settings[s_key] = widget.value

        self.pm.save()

    # ── Button handlers ──────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "btn-launch":
            self.action_launch_profile()
        elif btn_id == "btn-stop":
            self.pm.stop()
            self._refresh_list()
            if self._selected_profile:
                self._show_profile(self._selected_profile)
        elif btn_id == "btn-create":
            self.action_create_profile()
        elif btn_id == "btn-delete":
            self.action_delete_profile()

    def on_screen_resume(self, event: Screen.Resume) -> None:
        """Called when returning from a modal."""
        pass

    # ── Modal return handlers ────────────────────────────────────────

    def on_create_profile_screen_dismissed(self, result: dict | None) -> None:
        if result:
            err = self.pm.create(result["name"], result["template"], result["desc"])
            if err:
                self.query_one("#status-bar", Label).update(f"ERROR: {err}")
                self.query_one("#status-bar", Label).styles.color = "#da3633"
            else:
                self._selected_profile = result["name"]
                self._refresh_list()
                self._show_profile(result["name"])

    def on_confirm_delete_screen_dismissed(self, confirmed: bool) -> None:
        if confirmed and self._selected_profile:
            self.pm.delete(self._selected_profile)
            self._selected_profile = None
            self._refresh_list()
            self.query_one("#detail-header", Static).update("(no selection)")
            self.query_one("#template-label", Label).update("")
            self.query_one("#settings-scroll", ScrollableContainer).remove_children()
            self._settings_widgets.clear()


# ═════════════════════════════════════════════════════════════════════
#  Entry point
# ═════════════════════════════════════════════════════════════════════

def main():
    if "--list" in sys.argv:
        pm = profile_manager()
        print(f"Profiles ({len(pm.profiles)}):")
        for p in pm.profiles:
            tmpl_name = "(unknown)"
            if 0 <= p.template < len(pm._template_mgr.incarnations):
                tmpl_name = pm._template_mgr.incarnations[p.template].name
            active = " ▶" if (p.name == pm.active and pm.is_running()) else ""
            print(f"  [{p.template}] {p.name}{active}")
            print(f"       {tmpl_name} | {p.description or '(no desc)'}")
        return
    app = ConfiguratorApp()
    app.run()


if __name__ == "__main__":
    main()
