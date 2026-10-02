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


_TOP_LEVEL_KEY_RE = re.compile(r"^([A-Za-z0-9_][\w.\-]*)\s*:")


def replace_top_level_block(
    raw_text: str, key: str, new_block: list[str]
) -> str | None:
    """Surgically replace (or append) a top-level YAML block, textually.

    *new_block* is the replacement block *including* its ``key:`` header
    line (each line should end with ``"\\n"``). Everything outside the
    block — comments, blank lines, other keys, their order — is preserved
    byte-for-byte.

    Returns the new file text, or ``None`` when the existing layout can't
    be handled cleanly; the caller should then fall back to a full
    ``yaml.safe_dump`` rewrite. ``None`` triggers:

    - the key appears indented (nested) anywhere — replacing only one
      occurrence could silently duplicate it;
    - the key appears more than once at the top level;
    - the block's extent can't be determined (a column-0 line inside the
      block that isn't another top-level key, ``---`` or ``...`` — e.g.
      a literal block scalar with unindented content).

    This is stdlib-only on purpose: no YAML parser is needed because we
    never interpret the block, we only swap its line span.
    """
    if not key or not _TOP_LEVEL_KEY_RE.fullmatch(key + ":"):
        return None
    header_re = re.compile(r"^" + re.escape(key) + r"\s*:(?=[\s#]|$)")
    nested_re = re.compile(r"^[ \t]+" + re.escape(key) + r"\s*:(?=[\s#]|$)")
    lines = raw_text.splitlines(keepends=True)

    def is_header(line: str) -> bool:
        return header_re.match(line) is not None

    top_hits: list[int] = []
    for i, line in enumerate(lines):
        if is_header(line):
            top_hits.append(i)
        elif nested_re.match(line):
            return None  # nested occurrence — ambiguous, bail out
    if len(top_hits) > 1:
        return None  # duplicate top-level keys — bail out

    block_lines = [ln if ln.endswith("\n") else ln + "\n" for ln in new_block]
    if not block_lines or not is_header(block_lines[0]):
        return None  # caller bug: replacement must carry the header

    if not top_hits:
        # Absent: append at end of file.
        out = list(lines)
        if out and not out[-1].endswith("\n"):
            out[-1] = out[-1] + "\n"
        out.extend(block_lines)
        return "".join(out)

    start = top_hits[0]
    end = len(lines)
    pending_comment: int | None = None
    i = start + 1
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if line[0] in (" ", "\t"):
            pending_comment = None  # indented content: comments so far are inside
            i += 1
            continue
        if stripped.startswith("#"):
            # Tentatively absorbed: if a top-level key / --- / ... / EOF
            # follows with no more indented content, the comment run
            # attaches to what follows and must be preserved.
            if pending_comment is None:
                pending_comment = i
            i += 1
            continue
        if stripped in ("---", "...") or _TOP_LEVEL_KEY_RE.match(line):
            end = pending_comment if pending_comment is not None else i
            break
        return None  # column-0 content that isn't a new block — bail out
    else:
        if pending_comment is not None:
            end = pending_comment  # trailing comment run at EOF is preserved
    return "".join(lines[:start] + block_lines + lines[end:])


__all__ = [
    "validate_name",
    "parse_args_text",
    "format_args_text",
    "build_entry_dict",
    "summarize_command",
    "replace_top_level_block",
]
