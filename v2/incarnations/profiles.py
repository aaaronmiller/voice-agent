#!/usr/bin/env python3
"""Profile management — named configs referencing incarnation templates.

Each profile selects an incarnation template (by index) and overrides
any of its settings. Profiles can be saved, loaded, launched by name.

Usage:
  from incarnations.profiles import ProfileManager, profile_manager

  pm = profile_manager()
  pm.create("quick-talker", template=0, description="Fast responses",
            settings={"tts.speed": 1.6, "barge_in.enabled": False})
  pm.launch("quick-talker")
"""

from __future__ import annotations

import json
import logging
import os
import platform
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ── Paths (inlined from chooser to avoid relative import issues) ──
_REPO_DIR = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _REPO_DIR / "incarnations.yaml"
_ENV_FILE_PATH = _REPO_DIR / ".env"
_PLATFORM = platform.system().lower()
_IS_LINUX = _PLATFORM == "linux"
_IS_WSL = "microsoft" in platform.uname().release.lower() if _IS_LINUX else False

log = logging.getLogger("profiles")

_PROFILES_PATH = _REPO_DIR / "profiles.yaml"


@dataclass
class Profile:
    """A named profile referencing an incarnation template + setting overrides."""
    name: str
    template: int  # index into incarnations.yaml incarnations[]. Must be 0..n-1
    description: str
    settings: dict[str, Any] = field(default_factory=dict)


class ProfileManager:
    """Loading, saving, creating, deleting, renaming, and launching profiles."""

    def __init__(self, profiles_path: Path = _PROFILES_PATH):
        self.profiles_path = profiles_path
        self.profiles: list[Profile] = []
        self.active: str = ""  # currently launched profile name, or ""
        # Lazy import to avoid circular dependency
        from incarnations.chooser import IncarnationManager
        self._template_mgr = IncarnationManager()  # lives inside chooser
        self._process: subprocess.Popen | None = None
        self._proc_start: float = 0.0
        self.load()

    # ── Persistence ────────────────────────────────────────────────────

    def load(self) -> None:
        if not self.profiles_path.exists():
            self._create_defaults()
            return
        try:
            with open(self.profiles_path) as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            data = {}
        self.active = data.get("active", "")
        self.profiles = []
        for raw in data.get("profiles", []):
            self.profiles.append(Profile(
                name=raw.get("name", "Unnamed"),
                template=raw.get("template", 0),
                description=raw.get("description", ""),
                settings=raw.get("settings", {}),
            ))
        # Ensure at least one profile
        if not self.profiles:
            self._create_defaults()

    def save(self) -> None:
        data = {"active": self.active, "profiles": []}
        for p in self.profiles:
            data["profiles"].append({
                "name": p.name,
                "template": p.template,
                "description": p.description,
                "settings": p.settings,
            })
        self.profiles_path.write_text(
            "# BabelFish Profiles — named configurations\n"
            + yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
        )
        log.info(f"Saved {len(self.profiles)} profiles to {self.profiles_path}")

    def _create_defaults(self) -> None:
        """Seed with sensible defaults based on available templates."""
        default_templates = [
            (0, "Raccoon Standard",
             "v2 stack: Whisper → Hermes → Kokoro TTS + raccoon avatar. Reliable daily driver."),
            (2, "Gemini Thinker",
             "Google Gemini Multimodal Live API: voice-in→voice-out, no STT/TTS overhead. ~500ms-2s latency."),
        ]
        for tmpl, name, desc in default_templates:
            if tmpl < len(self._template_mgr.incarnations):
                self.profiles.append(Profile(name=name, template=tmpl, description=desc))
        self.save()

    # ── CRUD ───────────────────────────────────────────────────────────

    def list(self) -> list[Profile]:
        return self.profiles

    def get(self, name: str) -> Profile | None:
        for p in self.profiles:
            if p.name == name:
                return p
        return None

    def create(self, name: str, template: int,
               description: str = "", settings: dict[str, Any] | None = None) -> str | None:
        """Create a new profile. Returns error string or None on success."""
        if self.get(name):
            return f"Profile {name!r} already exists"
        if template < 0 or template >= len(self._template_mgr.incarnations):
            return f"Template index {template} out of range (0-{len(self._template_mgr.incarnations) - 1})"
        self.profiles.append(Profile(
            name=name,
            template=template,
            description=description,
            settings=settings or {},
        ))
        self.save()
        return None

    def delete(self, name: str) -> str | None:
        p = self.get(name)
        if not p:
            return f"Profile {name!r} not found"
        self.profiles = [x for x in self.profiles if x.name != name]
        if self.active == name:
            self.active = ""
        self.save()
        return None

    def rename(self, old_name: str, new_name: str) -> str | None:
        p = self.get(old_name)
        if not p:
            return f"Profile {old_name!r} not found"
        if self.get(new_name):
            return f"Profile {new_name!r} already exists"
        p.name = new_name
        if self.active == old_name:
            self.active = new_name
        self.save()
        return None

    def set_setting(self, name: str, key: str, value: Any) -> str | None:
        p = self.get(name)
        if not p:
            return f"Profile {name!r} not found"
        p.settings[key] = value
        self.save()
        return None

    def update_settings(self, name: str, updates: dict[str, Any]) -> str | None:
        p = self.get(name)
        if not p:
            return f"Profile {name!r} not found"
        p.settings.update(updates)
        self.save()
        return None

    # ── Launch / Stop ─────────────────────────────────────────────────

    def launch(self, name: str) -> str | None:
        """Launch a profile by name. Returns error string or None on success."""
        self.stop()
        time.sleep(0.5)

        p = self.get(name)
        if not p:
            return f"Profile {name!r} not found"
        if p.template < 0 or p.template >= len(self._template_mgr.incarnations):
            return f"Template index {p.template} out of range"

        tmpl = self._template_mgr.incarnations[p.template]
        cmd = tmpl.get_command()
        if not cmd:
            return f"No command for platform {_PLATFORM}"

        # ── Build env: template defaults + profile overrides ──
        env = os.environ.copy()
        # Apply template defaults
        for s_key, sd in tmpl.settings.items():
            env[s_key.upper().replace(".", "_")] = str(sd.default)
        # Apply profile overrides
        for s_key, val in p.settings.items():
            env[s_key.upper().replace(".", "_")] = str(val)

        # ── Resolve command template vars ──
        cwd_abs = str((_REPO_DIR / tmpl.cwd).resolve())
        cmd = cmd.replace("${CWD}", cwd_abs)
        for key, val in p.settings.items():
            env_key = key.upper().replace(".", "_")
            cmd = cmd.replace(f"${{{env_key}}}", str(val))

        # ── Launch ──
        log_path = _REPO_DIR / tmpl.log_file
        log_path.parent.mkdir(exist_ok=True)
        try:
            log.info(f"Launching profile {name!r} (template #{p.template}: {tmpl.name})")
            self._process = subprocess.Popen(
                cmd, shell=True, cwd=cwd_abs, env=env,
                stdout=open(log_path, "a"), stderr=subprocess.STDOUT,
                preexec_fn=(os.setpgrp if not _IS_WSL else None),
            )
            self._proc_start = time.time()
            self.active = name
            self.save()
            self._write_env_file(p, tmpl, cwd_abs)
            return None
        except Exception as e:
            self._process = None
            self.active = ""
            return str(e)

    def stop(self) -> None:
        if self._process is None:
            return
        log.info(f"Stopping profile process (PID={self._process.pid})...")
        try:
            if not _IS_WSL:
                os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
            else:
                self._process.terminate()
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                if not _IS_WSL:
                    os.killpg(os.getpgid(self._process.pid), signal.SIGKILL)
                else:
                    self._process.kill()
            except (ProcessLookupError, PermissionError):
                pass
        except (ProcessLookupError, PermissionError):
            pass
        self._process = None
        self._proc_start = 0.0
        self.active = ""
        self.save()

    def is_running(self) -> bool:
        if self._process is None:
            return False
        return self._process.poll() is None

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self._proc_start if self._process and self.is_running() else 0.0

    def _write_env_file(self, p: Profile, tmpl: Any, cwd_abs: str) -> None:
        try:
            with open(_ENV_FILE_PATH, "w") as f:
                f.write(f"# BabelFish active profile: {p.name}\n")
                f.write(f"BABELFISH_PROFILE={p.name}\n")
                f.write(f"BABELFISH_TEMPLATE={p.template}\n")
                for key, val in p.settings.items():
                    f.write(f'{key.upper().replace(".", "_")}="{val}"\n')
                if self._process:
                    f.write(f'BABELFISH_PID="{self._process.pid}"\n')
                f.write(f'BABELFISH_CWD="{cwd_abs}"\n')
        except Exception:
            pass


# ── Singleton ────────────────────────────────────────────────────────

_manager: ProfileManager | None = None


def profile_manager() -> ProfileManager:
    global _manager
    if _manager is None:
        _manager = ProfileManager()
    return _manager
