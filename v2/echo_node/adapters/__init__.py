"""External providers for Echo-Node v2 (Phases B + D).

An *external provider* is declared in the config file — the trust
boundary — and never typed into the settings UI. Two transports:

* ``transport: subprocess`` (default, Phase B): any program speaking the
  JSON-RPC 2.0 adapter protocol over stdio.

    .. code-block:: yaml

        external_providers:
          - slot: stt
            name: whispercpp
            command: ["builtin:stt_whispercpp.py"]
            args: ["--model", "/models/ggml-base.bin"]

* ``transport: tcp`` (Phase D): a Wyoming-protocol server
  (wyoming-faster-whisper, wyoming-piper, wyoming-openwakeword, ...).
  No command is spawned — the adapter only opens a TCP connection.

    .. code-block:: yaml

        external_providers:
          - slot: stt
            name: wy-faster-whisper
            transport: tcp
            host: 127.0.0.1   # default
            port: 10300        # required (conventional Wyoming ports:
                               # faster-whisper 10300, piper 10200,
                               # openwakeword 10400)

At startup :func:`register_external_providers` validates each entry and
registers a provider class into the slot registry with
``external=True``. Validated externals then appear in the existing
registry-driven settings dropdowns automatically (marked " (external)").
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

from echo_node.slots import SlotType

ADAPTERS_DIR = Path(__file__).resolve().parent

# Repo-shipped reference adapters. ``builtin:<name>`` resolves to
# ``v2/echo_node/adapters/<name>`` run under sys.executable. The
# allowlist is exact: no ``..``, no separators, no absolute paths,
# and the name must be one of these.
BUILTIN_ADAPTERS = frozenset({
    "stt_whispercpp.py",
    "tts_piper.py",
    "stt_reference.py",
})

_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]*")


class ExternalProviderError(ValueError):
    """A config entry in ``external_providers:`` is invalid."""


def resolve_command(command: list[str], args: list[str], *, name: str) -> list[str]:
    """Resolve an entry's ``command`` + ``args`` to a final argv list.

    ``command[0]`` may be ``builtin:<file>`` — resolved to the shipped
    adapter under :data:`ADAPTERS_DIR` and run with ``sys.executable``.
    Anything else must be an explicit argv list from the config file
    (the trust boundary — see PROTOCOL.md).
    """
    if not command:
        raise ExternalProviderError(
            f"external provider {name!r}: 'command' must be a non-empty list")
    if not all(isinstance(c, str) and c for c in command):
        raise ExternalProviderError(
            f"external provider {name!r}: 'command' must be a list of non-empty strings")
    if not all(isinstance(a, str) for a in args):
        raise ExternalProviderError(
            f"external provider {name!r}: 'args' must be a list of strings")

    first = command[0]
    if first.startswith("builtin:"):
        raw = first[len("builtin:"):]
        if (not raw or raw not in BUILTIN_ADAPTERS
                or "/" in raw or "\\" in raw or raw.startswith(".")
                or os.path.isabs(raw)):
            raise ExternalProviderError(
                f"external provider {name!r}: invalid builtin {first!r} — "
                f"must be 'builtin:<file>' with <file> one of "
                f"{sorted(BUILTIN_ADAPTERS)} (no paths, no '..')")
        resolved = str(ADAPTERS_DIR / raw)
        return [sys.executable, resolved, *command[1:], *args]
    return [*command, *args]


def _validate_entry(raw: Any, index: int) -> dict[str, Any]:
    """Validate one ``external_providers`` entry; return the normalized dict."""
    where = f"external_providers[{index}]"
    if not isinstance(raw, dict):
        raise ExternalProviderError(f"{where}: entry must be a mapping, got {type(raw).__name__}")

    slot_raw = raw.get("slot")
    try:
        slot = SlotType(str(slot_raw))
    except ValueError:
        raise ExternalProviderError(
            f"{where}: unknown slot {slot_raw!r} — must be one of "
            f"{sorted(s.value for s in SlotType)}") from None

    # NOTE: slot-vs-transport support is checked per transport below
    # (subprocess vs tcp), not here.

    name = raw.get("name")
    if not isinstance(name, str) or not _NAME_RE.fullmatch(name):
        raise ExternalProviderError(
            f"{where}: 'name' must match [A-Za-z0-9][A-Za-z0-9_.-]*, got {name!r}")

    protocol_version = raw.get("protocol_version", 1)
    if protocol_version != 1:
        raise ExternalProviderError(
            f"{where}: unsupported protocol_version {protocol_version!r} — "
            f"this host speaks version 1")

    transport = raw.get("transport", "subprocess")
    if transport not in ("subprocess", "tcp"):
        raise ExternalProviderError(
            f"{where}: 'transport' must be 'subprocess' or 'tcp', "
            f"got {transport!r}")

    def _num(key: str, default: float) -> float:
        val = raw.get(key, default)
        try:
            return float(val)
        except (TypeError, ValueError):
            raise ExternalProviderError(f"{where}: {key!r} must be a number, got {val!r}") from None

    def _str_list(key: str) -> list[str]:
        val = raw.get(key, [])
        if not isinstance(val, list) or not all(
                isinstance(v, str) and v for v in val):
            raise ExternalProviderError(
                f"{where}: {key!r} must be a list of non-empty strings, "
                f"got {val!r}")
        return list(val)

    common = {
        "name": name,
        "slot": slot.value,
        "slot_enum": slot,
        "transport": transport,
        "request_timeout_s": _num("request_timeout_s", 30.0),
        "label": raw.get("label") or name,
        "experimental": bool(raw.get("experimental", False)),
        "capabilities": raw.get("capabilities") or {},
    }

    if transport == "tcp":
        return _validate_tcp_entry(raw, where, common, _num, _str_list)

    from echo_node.adapters.subprocess_adapter import SUPPORTED_SLOTS
    if slot not in SUPPORTED_SLOTS:
        raise ExternalProviderError(
            f"{where}: slot {slot.value!r} cannot be served by a subprocess "
            f"adapter (supported: "
            f"{sorted(s.value for s in SUPPORTED_SLOTS)})")

    command = raw.get("command", [])
    args = raw.get("args", [])
    if not isinstance(command, list):
        raise ExternalProviderError(f"{where}: 'command' must be a list, got {type(command).__name__}")
    if not isinstance(args, list):
        raise ExternalProviderError(f"{where}: 'args' must be a list, got {type(args).__name__}")
    argv = resolve_command(command, args, name=name)

    return {
        **common,
        "argv": argv,
        "idle_timeout_s": _num("idle_timeout_s", 120.0),
        "max_restarts": int(_num("max_restarts", 3)),
    }


def _validate_tcp_entry(
    raw: dict[str, Any],
    where: str,
    common: dict[str, Any],
    _num: Any,
    _str_list: Any,
) -> dict[str, Any]:
    """Validate a ``transport: tcp`` entry (Wyoming server)."""
    from echo_node.adapters.wyoming import TCP_SUPPORTED_SLOTS

    slot = common["slot_enum"]
    name = common["name"]
    if slot not in TCP_SUPPORTED_SLOTS:
        raise ExternalProviderError(
            f"{where}: slot {slot.value!r} cannot be served over Wyoming TCP "
            f"(supported: {sorted(s.value for s in TCP_SUPPORTED_SLOTS)})")

    command = raw.get("command", [])
    if command:
        raise ExternalProviderError(
            f"{where}: transport 'tcp' takes no 'command' — the adapter only "
            f"opens a TCP connection to host:port; nothing is spawned")
    args = raw.get("args", [])
    if args:
        raise ExternalProviderError(
            f"{where}: transport 'tcp' takes no 'args' (there is no command "
            f"to pass them to)")

    host = raw.get("host", "127.0.0.1")
    if not isinstance(host, str) or not host.strip():
        raise ExternalProviderError(
            f"{where}: 'host' must be a non-empty string, got {host!r}")

    port_raw = raw.get("port")
    if port_raw is None:
        raise ExternalProviderError(
            f"{where}: transport 'tcp' requires 'port' (conventional Wyoming "
            f"ports: faster-whisper 10300, piper 10200, openwakeword 10400)")
    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        raise ExternalProviderError(
            f"{where}: 'port' must be an integer 1-65535, got {port_raw!r}") from None
    if not 1 <= port <= 65535:
        raise ExternalProviderError(
            f"{where}: 'port' must be an integer 1-65535, got {port_raw!r}")

    return {
        **common,
        "host": host,
        "port": port,
        "connect_timeout_s": _num("connect_timeout_s", 3.0),
        "chunk_samples": max(1, int(_num("chunk_samples", 1024))),
        # Optional Wyoming hints, passed through to the protocol events:
        # stt -> transcribe {name, language}; tts -> synthesize.voice;
        # wake_word -> detect {names}.
        "model": raw.get("model"),
        "language": raw.get("language"),
        "voice_name": raw.get("voice_name"),
        "voice_speaker": raw.get("voice_speaker"),
        "phrase_names": _str_list("phrase_names"),
    }


def register_external_providers(
    config: dict[str, Any],
    reg: Any | None = None,
) -> list[str]:
    """Validate ``config['external_providers']`` and register each entry.

    Returns the list of registered ``"<slot>/<name>"`` strings (empty
    when the config declares none). Raises :class:`ExternalProviderError`
    with a clear message on any schema violation or name collision —
    startup should treat that as fatal.
    """
    from echo_node.adapters.subprocess_adapter import make_external_provider
    from echo_node.adapters.wyoming import make_wyoming_provider
    from echo_node.slots.registry import get_registry

    reg = reg if reg is not None else get_registry()
    raw_entries = config.get("external_providers") or []
    if not isinstance(raw_entries, list):
        raise ExternalProviderError(
            f"'external_providers' must be a list, got {type(raw_entries).__name__}")
    registered: list[str] = []
    for index, raw in enumerate(raw_entries):
        entry = _validate_entry(raw, index)
        slot, name = entry["slot_enum"], entry["name"]
        try:
            reg.info(slot, name)
        except KeyError:
            pass
        else:
            raise ExternalProviderError(
                f"external provider {name!r} collides with an existing "
                f"{slot.value} provider — rename it in 'external_providers'")
        cls = (make_wyoming_provider(entry) if entry["transport"] == "tcp"
               else make_external_provider(entry))
        reg.register(slot, name, cls,
                     experimental=entry["experimental"],
                     external=True)
        registered.append(f"{slot.value}/{name}")
    return registered


__all__ = [
    "ADAPTERS_DIR",
    "BUILTIN_ADAPTERS",
    "ExternalProviderError",
    "resolve_command",
    "register_external_providers",
]
