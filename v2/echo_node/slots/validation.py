"""Graceful provider validators for the Echo-Node slot registry.

Every check here is designed for a machine that may have no GPU, no audio
hardware, and no models downloaded. The rules:

  - never download anything,
  - never raise — return an honest "missing X" result instead,
  - probes that touch the network use a short timeout,
  - probes that need hardware report its absence as a failed check,
    not an exception.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationResult:
    ok: bool
    reason: str
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "reason": self.reason, "details": self.details}


# ── Primitive checks ────────────────────────────────────────────────

def check_module(module_name: str) -> tuple[bool, str]:
    """Is *module_name* importable? Returns (found, version-or-reason)."""
    try:
        spec = importlib.util.find_spec(module_name)
    except Exception as exc:  # e.g. parent package raises on import
        return False, f"{module_name} not importable: {exc}"
    if spec is None:
        return False, f"{module_name} is not installed"
    # Only read __version__ if the module is already imported — never
    # execute module code as a side effect of a probe.
    import sys
    already = sys.modules.get(module_name)
    version = str(getattr(already, "__version__", "unknown")) if already is not None else "unknown"
    return True, version


def check_binary(name: str) -> tuple[bool, str]:
    """Is *name* on PATH? Returns (found, path-or-reason)."""
    path = shutil.which(name)
    if path:
        return True, path
    return False, f"{name} not found on PATH"


def check_paths(*paths: str) -> list[str]:
    """Return the subset of *paths* that do not exist."""
    import pathlib
    return [p for p in paths if not pathlib.Path(p).exists()]


def check_env(*names: str) -> list[str]:
    """Return the subset of env vars in *names* that are unset/empty."""
    return [n for n in names if not os.environ.get(n)]


def check_http(url: str, timeout: float = 2.0) -> tuple[bool, str]:
    """Probe an HTTP(S) endpoint. Never raises."""
    try:
        import requests
        r = requests.get(url, timeout=timeout)
        if r.status_code < 500:
            return True, f"HTTP {r.status_code}"
        return False, f"HTTP {r.status_code}"
    except Exception as exc:
        return False, f"unreachable: {exc}"


def check_cuda() -> tuple[bool, str]:
    """Is torch CUDA available? Never raises."""
    found, _ = check_module("torch")
    if not found:
        return False, "torch is not installed"
    try:
        import torch
        if torch.cuda.is_available():
            return True, torch.cuda.get_device_name(0)
        return False, "torch installed but CUDA is not available"
    except Exception as exc:
        return False, f"torch CUDA probe failed: {exc}"


def missing_result(what: str, details: dict[str, Any] | None = None) -> ValidationResult:
    return ValidationResult(False, f"missing {what}", details or {})


def ok_result(reason: str = "ok", details: dict[str, Any] | None = None) -> ValidationResult:
    return ValidationResult(True, reason, details or {})
