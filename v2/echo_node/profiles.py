"""Loader + validator for voice-profile/v1 documents (T004 contract).

Contract: specs/voice-unification/contracts/profiles.md.
Profiles live at specs/voice-unification/profiles/*.yaml.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

FORMAT = "voice-profile/v1"

KEY_ORDER = [
    "format", "name", "version", "description", "stack", "dialogue",
    "params", "secrets", "hardware_floor", "covers", "evidence",
]

STACK_SLOTS = (
    "wake_word", "vad", "stt", "tts", "agent_backend", "avatar",
    "audio_io", "barge_in",
)

SECRET_RE = re.compile(r"^(env|keyring|file):[^ ]+$")


class ProfileError(ValueError):
    pass


def _need_yaml() -> None:
    if yaml is None:
        raise ProfileError("pyyaml required to load profiles")


def load_profile(path: str | Path) -> dict[str, Any]:
    """Load + validate one profile document. Returns the mapping."""
    _need_yaml()
    text = Path(path).read_text(encoding="utf-8")
    doc = yaml.safe_load(text)
    validate_profile(doc, source=str(path))
    return doc


def validate_profile(doc: Any, source: str = "<doc>") -> None:
    """Raise ProfileError naming the bad field; never echo secret values."""
    if not isinstance(doc, dict):
        raise ProfileError(f"{source}: document must be a mapping")
    if doc.get("format") != FORMAT:
        raise ProfileError(f"{source}: field 'format' must be {FORMAT!r}")
    for field in ("name", "version", "description"):
        if field not in doc:
            raise ProfileError(f"{source}: missing field {field!r}")
    if not isinstance(doc["version"], int):
        raise ProfileError(f"{source}: field 'version' must be an integer")

    stack = doc.get("stack")
    if not isinstance(stack, dict):
        raise ProfileError(f"{source}: field 'stack' must be a mapping")
    for slot in STACK_SLOTS:
        if slot not in stack:
            raise ProfileError(f"{source}: stack missing slot {slot!r}")
        if not isinstance(stack[slot], str) or not stack[slot]:
            raise ProfileError(f"{source}: stack.{slot} must be a non-empty name")

    dialogue = doc.get("dialogue")
    if not isinstance(dialogue, dict):
        raise ProfileError(f"{source}: field 'dialogue' must be a mapping")
    for field in ("provider", "transport"):
        if not isinstance(dialogue.get(field), str) or not dialogue[field]:
            raise ProfileError(f"{source}: dialogue.{field} must be a non-empty string")

    params = doc.get("params", {})
    if not isinstance(params, dict):
        raise ProfileError(f"{source}: field 'params' must be a mapping")
    for key in params:
        if not isinstance(key, str) or "." not in key:
            raise ProfileError(f"{source}: params key {key!r} must be a dotted config path")

    secrets = doc.get("secrets", {})
    if not isinstance(secrets, dict):
        raise ProfileError(f"{source}: field 'secrets' must be a mapping")
    for key, value in secrets.items():
        # Name the field; never include the value in the error.
        if not isinstance(value, str) or not SECRET_RE.match(value):
            raise ProfileError(
                f"{source}: secrets field {key!r} must be a reference "
                f"(env:...|keyring:...|file:...), not an inline value")

    floor = doc.get("hardware_floor")
    if not isinstance(floor, dict):
        raise ProfileError(f"{source}: field 'hardware_floor' must be a mapping")

    covers = doc.get("covers", [])
    if not isinstance(covers, list) or not all(isinstance(c, str) for c in covers):
        raise ProfileError(f"{source}: field 'covers' must be a string list")

    evidence = doc.get("evidence", [])
    if not isinstance(evidence, list):
        raise ProfileError(f"{source}: field 'evidence' must be a list")


def dump_profile(doc: dict[str, Any]) -> str:
    """Canonical serialization: frozen key order, UTF-8, LF."""
    _need_yaml()
    ordered = {k: doc[k] for k in KEY_ORDER if k in doc}
    for k, v in doc.items():
        if k not in ordered:
            ordered[k] = v
    text = yaml.safe_dump(ordered, sort_keys=False, allow_unicode=True)
    if not text.endswith("\n"):
        text += "\n"
    return text


def export_profile(doc: dict[str, Any], path: str | Path) -> Path:
    out = Path(path)
    out.write_text(dump_profile(doc), encoding="utf-8")
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in ("validate",):
        print("usage: python3 -m echo_node.profiles validate <file>...",
              file=sys.stderr)
        args = argv[1:]
        if not args or args[0] != "validate" or len(args) < 2:
            return 2
        code = 0
        for path in args[1:]:
            try:
                load_profile(path)
                print(f"{path}: VALID")
            except ProfileError as exc:
                print(f"{path}: INVALID: {exc}")
                code = 1
        return code
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
