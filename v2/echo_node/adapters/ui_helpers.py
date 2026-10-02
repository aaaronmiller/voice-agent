"""Qt-free helpers for the External-providers settings UI (Phase C).

This module is deliberately importable **without** PyQt6 and without any
``echo_node`` imports (stdlib only): the Add/Edit dialog and the External
tab in ``avatar/settings_popup.py`` share this logic, and the unit tests
in ``echo_node/tests/test_external_ui_logic.py`` exercise it on machines
with no Qt at all.

The dicts built here are config-shaped ``external_providers:`` entries —
the same shape ``echo_node.adapters._validate_entry`` accepts — so the
UI, the tests, and the config file all speak one schema.
"""

from __future__ import annotations

import re
from typing import Any

# Same pattern as echo_node.adapters._NAME_RE (duplicated so this module
# stays dependency-free; the assistant side re-validates anyway).
_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]*")


def validate_name(name: Any) -> str | None:
    """Return an error message, or None when *name* is a legal provider name."""
    if not isinstance(name, str) or not name:
        return "name must not be empty"
    if not _NAME_RE.fullmatch(name):
        return "name must match [A-Za-z0-9][A-Za-z0-9_.-]* (letters, digits, _, ., -)"
    return None


def parse_args_text(text: str) -> list[str]:
    """Parse the one-argument-per-line editor content into an argv list.

    Blank lines are dropped; leading/trailing whitespace is stripped.
    No shell splitting is done — one line is exactly one argument, so
    values containing spaces are safe.
    """
    return [ln.strip() for ln in str(text).splitlines() if ln.strip()]


def format_args_text(args: list[str] | tuple[str, ...]) -> str:
    """Inverse of :func:`parse_args_text` — for prefilling the editor."""
    return "\n".join(str(a) for a in args)


def build_entry_dict(
    *,
    slot: str,
    name: str,
    command: list[str],
    args: list[str] | None = None,
    protocol_version: int = 1,
    request_timeout_s: float = 30.0,
    idle_timeout_s: float = 120.0,
    max_restarts: int = 3,
    label: str | None = None,
    experimental: bool = False,
    capabilities: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a config-shaped ``external_providers`` entry.

    *command* is the argv list for the child (``["builtin:<file>"]`` for a
    repo-shipped adapter, or an explicit executable + fixed flags);
    *args* holds the extra per-deployment arguments. Values are copied so
    later edits of the caller's lists can't alias the entry.
    """
    return {
        "slot": slot,
        "name": name,
        "command": list(command),
        "args": list(args) if args else [],
        "protocol_version": int(protocol_version),
        "request_timeout_s": float(request_timeout_s),
        "idle_timeout_s": float(idle_timeout_s),
        "max_restarts": int(max_restarts),
        "label": label or name,
        "experimental": bool(experimental),
        "capabilities": dict(capabilities) if capabilities else {},
    }


def summarize_command(argv: list[str] | tuple[str, ...]) -> str:
    """One-line human summary of an argv list for list views.

    Truncated at 72 characters so rows stay readable; empty argv renders
    as an explicit placeholder rather than a blank row.
    """
    if not argv:
        return "(no command)"
    text = " ".join(str(a) for a in argv)
    if len(text) <= 72:
        return text
    return text[:69] + "..."


__all__ = [
    "validate_name",
    "parse_args_text",
    "format_args_text",
    "build_entry_dict",
    "summarize_command",
]
