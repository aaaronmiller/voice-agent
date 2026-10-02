"""Wyoming-protocol TCP adapters for Echo-Node v2 (Phase D).

A *Wyoming server* (e.g. wyoming-faster-whisper, wyoming-piper,
wyoming-openwakeword — the Home Assistant voice ecosystem) takes a
pipeline slot over TCP. Config entries declare ``transport: tcp`` with
``host``/``port`` — the adapter opens a connection per request, speaks
the Wyoming event protocol, and closes it. Nothing is spawned; there
are no executable paths involved.

The ``wyoming`` PyPI package is deliberately NOT used: it was not
installed on the build machine, and a stdlib-only client keeps the
host dependency-free. Framing and event names were verified twice:
against the upstream source at 2026-10-01 (rhasspy/wyoming, now
OHF-Voice/wyoming, main branch — ``wyoming/event.py`` (framing),
``asr.py``, ``tts.py``, ``wake.py``, ``audio.py``) and again against the
``wyoming`` 1.10.2 wheel (event framing in ``event.py``, ``error`` event
shape in ``error.py``, ``detect``/``detection``/``not-detected`` in
``wake.py``). Where the protocol leaves room for doubt it is called out
in comments. No live-server round-trip has been done yet — that needs
real Wyoming servers on the target machine.
"""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from echo_node.adapters import protocol as _p
from echo_node.adapters.protocol import AdapterTimeout
from echo_node.slots import (
    Capability,
    SlotType,
    STTProvider,
    TTSProvider,
    WakeWordProvider,
)
from echo_node.slots.validation import (
    ValidationResult,
    missing_result,
    ok_result,
)

log = logging.getLogger("echo_node.adapters.wyoming")

# Sent as the "version" field on every event we write. Upstream servers
# ignore it on read; we send an honest identifier, not a fake version.
CLIENT_VERSION = "echo-node"

# Conventional Wyoming ports, per the projects' documented defaults
# (Home Assistant Wyoming add-ons). NOT re-verified against running
# servers in this session — confirm against the server you run.
CONVENTIONAL_PORTS = {
    "faster-whisper": 10300,   # wyoming-faster-whisper (STT)
    "piper": 10200,            # wyoming-piper (TTS)
    "openwakeword": 10400,     # wyoming-openwakeword (wake word)
}

DEFAULT_CONNECT_TIMEOUT_S = 3.0
DEFAULT_REQUEST_TIMEOUT_S = 30.0
DEFAULT_CHUNK_SAMPLES = 1024  # 64 ms at 16 kHz


# ── Errors ──────────────────────────────────────────────────────────

class WyomingError(Exception):
    """Base for Wyoming transport errors."""


class WyomingConnectionError(WyomingError):
    """TCP connect failed (refused, unreachable, DNS, ...)."""


class WyomingProtocolError(WyomingError):
    """The server spoke something that is not the Wyoming protocol,
    closed the connection mid-request, or answered with an `error`
    event. (The `error` event shape — type "error", data {"text",
    "code"} — was verified against wyoming 1.10.2's error.py; a
    live-server round-trip is still untested.)"""


# ── Framing ─────────────────────────────────────────────────────────
#
# Upstream framing (wyoming/event.py): one JSON line
#   {"type": <str>, "version": <str>, "data_length": N,
#    "payload_length": M}           <- payload_length only when > 0
# followed by N bytes of JSON (the "data" dict), then M bytes of raw
# payload (audio bytes for audio-chunk). The reader merges the data
# blob into event.data and attaches the payload separately.

@dataclass
class WyomingEvent:
    type: str
    data: dict[str, Any] = field(default_factory=dict)
    payload: bytes | None = None


def write_event(
    sock: socket.socket,
    event_type: str,
    data: dict[str, Any] | None = None,
    payload: bytes | None = None,
) -> None:
    """Write one Wyoming event: header line + data blob + payload."""
    data_bytes = b""
    if data:
        data_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
    header = {
        "type": event_type,
        "version": CLIENT_VERSION,
        "data_length": len(data_bytes),
    }
    if payload:
        header["payload_length"] = len(payload)
    sock.sendall(json.dumps(header, ensure_ascii=False).encode("utf-8") + b"\n")
    if data_bytes:
        sock.sendall(data_bytes)
    if payload:
        sock.sendall(payload)


class _SockReader:
    """Deadline-bounded buffered reader over a blocking socket."""

    def __init__(self, sock: socket.socket, timeout: float) -> None:
        self._sock = sock
        self._buf = bytearray()
        self._deadline = time.monotonic() + max(0.0, timeout)

    def _fill(self, want: int) -> None:
        while len(self._buf) < want:
            remaining = self._deadline - time.monotonic()
            if remaining <= 0:
                raise AdapterTimeout("wyoming read timed out")
            self._sock.settimeout(remaining)
            # Never read past `want`: a fresh _SockReader is created per
            # read_event() call, so any over-read bytes would be silently
            # discarded — swallowing the start of the next event.
            chunk = self._sock.recv(want - len(self._buf))
            if not chunk:
                raise WyomingProtocolError(
                    "wyoming server closed the connection mid-request")
            self._buf += chunk

    def read_line(self) -> bytes:
        while True:
            idx = self._buf.find(b"\n")
            if idx >= 0:
                line = bytes(self._buf[:idx])
                del self._buf[: idx + 1]
                return line
            self._fill(len(self._buf) + 1)

    def read_exactly(self, n: int) -> bytes:
        if n <= 0:
            return b""
        self._fill(n)
        out = bytes(self._buf[:n])
        del self._buf[:n]
        return out


def read_event(sock: socket.socket, timeout: float) -> WyomingEvent:
    """Read one Wyoming event, bounded by *timeout* seconds total."""
    reader = _SockReader(sock, timeout)
    line = reader.read_line()
    try:
        header = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise WyomingProtocolError(
            f"wyoming server sent a non-JSON event line: {line[:80]!r}") from exc
    if not isinstance(header, dict) or "type" not in header:
        raise WyomingProtocolError(
            f"wyoming server sent a malformed event header: {line[:80]!r}")
    data: dict[str, Any] = {}
    # Defensive: upstream always sends data_length, but a missing/0
    # value must not hang the reader.
    data_length = header.get("data_length") or 0
    payload_length = header.get("payload_length") or 0
    if data_length:
        try:
            data = json.loads(reader.read_exactly(int(data_length)).decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise WyomingProtocolError(
                "wyoming server sent a malformed event data blob") from exc
        if not isinstance(data, dict):
            raise WyomingProtocolError(
                "wyoming server sent a non-object event data blob")
    payload = reader.read_exactly(int(payload_length)) or None
    return WyomingEvent(type=str(header["type"]), data=data, payload=payload)


# ── Connection ──────────────────────────────────────────────────────

class WyomingConnection:
    """One TCP connection to a Wyoming server.

    Connections are per-request: connect → send → read → close. This
    matches how the wyoming servers are used (one request stream per
    connection) and keeps failure modes simple — no reconnect state
    machine, no half-open sockets leaking across calls.
    """

    def __init__(self, host: str, port: int, *, name: str = "wyoming") -> None:
        self.host = host
        self.port = port
        self.name = name
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()

    @property
    def sock(self) -> socket.socket:
        assert self._sock is not None, "not connected"
        return self._sock

    def connect(self, timeout: float = DEFAULT_CONNECT_TIMEOUT_S) -> "WyomingConnection":
        try:
            self._sock = socket.create_connection(
                (self.host, self.port), timeout=timeout)
        except (socket.timeout, TimeoutError) as exc:
            raise AdapterTimeout(
                f"[{self.name}] connect to {self.host}:{self.port} timed out "
                f"after {timeout:.0f}s") from exc
        except OSError as exc:
            raise WyomingConnectionError(
                f"[{self.name}] cannot connect to "
                f"{self.host}:{self.port}: {exc}") from exc
        # Blocking mode from here on; per-read deadlines are enforced
        # by _SockReader.
        self._sock.settimeout(None)
        return self

    def close(self) -> None:
        with self._lock:
            sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass

    def __enter__(self) -> "WyomingConnection":
        return self.connect()

    def __exit__(self, *exc: Any) -> None:
        self.close()


# ── Adapter base ────────────────────────────────────────────────────

_CAPABILITY_FIELD_NAMES = ("name", "version", "languages", "streaming",
                           "vram_gb", "gpu_required", "license", "network", "notes")


class WyomingAdapter:
    """Shared behavior for all Wyoming-TCP-backed providers.

    Concrete classes are built by :func:`make_wyoming_provider`, which
    binds the config *entry* as the ``_entry`` class attribute:

        entry = {"name": ..., "slot": "stt", "transport": "tcp",
                 "host": "127.0.0.1", "port": 10300,
                 "connect_timeout_s": 3.0, "request_timeout_s": 30.0,
                 "chunk_samples": 1024, "model": None, "language": None,
                 "voice_name": None, "voice_speaker": None,
                 "phrase_names": [], "label": ..., "capabilities": {...}}
    """

    _entry: dict[str, Any] = {}

    def __init__(self, config: dict[str, Any]):
        self.config = dict(config)

    # ── connection ──

    @classmethod
    def _new_connection(cls) -> WyomingConnection:
        e = cls._entry
        return WyomingConnection(e["host"], e["port"], name=e["name"])

    # ── capabilities + validate ──

    @classmethod
    def capabilities(cls) -> Capability:
        e = cls._entry
        override = {k: v for k, v in (e.get("capabilities") or {}).items()
                    if k in _CAPABILITY_FIELD_NAMES}
        return Capability(
            name=e.get("name", cls.__name__),
            streaming=True,   # Wyoming is a streaming-audio protocol
            network=True,     # ... over TCP
            notes=(f"Wyoming-protocol TCP server at {e['host']}:{e['port']}; "
                   f"declared in config.yaml, never in the settings UI"),
            **override,
        )

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        """TCP connect probe — never raises, never downloads.

        A refused/timed-out connection is an honest missing-result, not
        an exception, so the provider simply stays out of the settings
        dropdowns until its server is running.
        """
        e = cls._entry
        target = f"{e['host']}:{e['port']}"
        conn = cls._new_connection()
        try:
            conn.connect(timeout=float(e.get("connect_timeout_s",
                                             DEFAULT_CONNECT_TIMEOUT_S)))
        except AdapterTimeout:
            return missing_result(
                f"wyoming server at {target} (connect timed out)",
                {"host": e["host"], "port": e["port"]})
        except WyomingError as exc:
            return missing_result(f"wyoming server at {target}",
                                  {"host": e["host"], "port": e["port"],
                                   "reason": str(exc)})
        except Exception as exc:  # never let a probe crash the registry
            return missing_result(f"wyoming server at {target}",
                                  {"host": e["host"], "port": e["port"],
                                   "reason": f"{type(exc).__name__}: {exc}"})
        finally:
            conn.close()
        return ok_result(f"wyoming {e['slot']} server reachable at {target}",
                         {"host": e["host"], "port": e["port"]})

    # ── event-flow helpers ──

    @staticmethod
    def _pcm16_bytes(samples: np.ndarray) -> bytes:
        """Mic chunk -> raw PCM16 bytes (16 kHz mono int16)."""
        a = np.asarray(samples)
        if a.dtype.kind == "f":
            a = np.clip(a, -1.0, 1.0) * 32767.0
        return np.asarray(a, dtype=np.int16).ravel().tobytes()

    def _send_audio_stream(
        self,
        conn: WyomingConnection,
        pcm: bytes,
        *,
        rate: int = 16000,
    ) -> None:
        """audio-start / audio-chunk+ / audio-stop for one utterance."""
        e = self._entry
        chunk_n = max(1, int(e.get("chunk_samples", DEFAULT_CHUNK_SAMPLES))) * 2
        write_event(conn.sock, "audio-start",
                    {"rate": rate, "width": 2, "channels": 1, "timestamp": 0})
        sent_samples = 0
        for off in range(0, len(pcm), chunk_n):
            chunk = pcm[off: off + chunk_n]
            write_event(
                conn.sock, "audio-chunk",
                {"rate": rate, "width": 2, "channels": 1,
                 "timestamp": int(sent_samples / rate * 1000)},
                payload=chunk,
            )
            sent_samples += len(chunk) // 2
        write_event(conn.sock, "audio-stop",
                    {"timestamp": int(sent_samples / rate * 1000)})

    def _read_until(
        self,
        conn: WyomingConnection,
        want: set[str],
        timeout: float,
    ) -> WyomingEvent:
        """Read events until one of *want* arrives.

        Unknown/other events (e.g. streaming variants we don't consume)
        are tolerated and skipped; an `error` event or a closed
        connection raises; exceeding *timeout* raises AdapterTimeout.
        """
        name = self._entry["name"]
        start = time.monotonic()
        while True:
            remaining = timeout - (time.monotonic() - start)
            if remaining <= 0:
                raise AdapterTimeout(
                    f"[{name}] timed out waiting for "
                    f"{sorted(want)} after {timeout:.0f}s")
            ev = read_event(conn.sock, remaining)
            if ev.type == "error":
                raise WyomingProtocolError(
                    f"[{name}] server error: {ev.data.get('text') or ev.data}")
            if ev.type in want:
                return ev
            log.debug(f"[{name}] skipping unexpected wyoming event {ev.type!r}")


# ── Per-slot adapter classes ─────────────────────────────────────────

class WyomingSTT(WyomingAdapter, STTProvider):
    """STT slot backed by a Wyoming ASR server (e.g. wyoming-faster-whisper).

    Flow: `transcribe` (+ optional name/language) → audio-start/chunk/stop
    → `transcript`. Streaming servers may also emit `transcript-chunk`
    (each chunk *replaces* the previous per upstream asr.py); the final
    `transcript` wins, a bare `transcript-stop` falls back to the last
    chunk.
    """

    def load(self) -> None:
        # Fail fast with a clear error if the server isn't there; the
        # per-call path would raise the same error on first use.
        result = self.validate()
        if not result.ok:
            raise WyomingConnectionError(
                f"[{self._entry['name']}] {result.reason}")

    def unload(self) -> None:
        pass  # connections are per-call; nothing to tear down

    def transcribe(self, wav_path) -> str:
        from pathlib import Path
        wav_path = Path(wav_path)
        e = self._entry
        timeout = float(e.get("request_timeout_s", DEFAULT_REQUEST_TIMEOUT_S))
        samples, _rate = _p.read_wav_pcm16(wav_path, target_rate=16000)

        data: dict[str, Any] = {}
        if e.get("model"):
            data["name"] = e["model"]      # upstream: Transcribe.name
        if e.get("language"):
            data["language"] = e["language"]

        conn = self._new_connection()
        conn.connect(timeout=float(e.get("connect_timeout_s",
                                         DEFAULT_CONNECT_TIMEOUT_S)))
        try:
            write_event(conn.sock, "transcribe", data)
            self._send_audio_stream(conn, samples.tobytes())
            chunk_text = ""
            while True:
                ev = self._read_until(
                    conn, {"transcript", "transcript-chunk", "transcript-stop"},
                    timeout)
                if ev.type == "transcript":
                    return str(ev.data.get("text", "")).strip()
                if ev.type == "transcript-chunk":
                    chunk_text = str(ev.data.get("text", ""))
                else:  # transcript-stop with no final transcript
                    return chunk_text.strip()
        finally:
            conn.close()


class WyomingTTS(WyomingAdapter, TTSProvider):
    """TTS slot backed by a Wyoming TTS server (e.g. wyoming-piper).

    Flow: `synthesize` (text + optional voice) → audio-start/chunk/stop
    → concatenated PCM written as WAV at the server's sample rate.
    Only 16-bit mono server output is supported (what wyoming-piper
    sends); anything else is a clear WyomingProtocolError.
    """

    def load(self) -> None:
        result = self.validate()
        if not result.ok:
            raise WyomingConnectionError(
                f"[{self._entry['name']}] {result.reason}")

    def unload(self) -> None:
        pass

    def warm(self) -> None:
        result = self.validate()
        if not result.ok:
            raise WyomingConnectionError(
                f"[{self._entry['name']}] {result.reason}")

    def synthesize_to_wav(self, text: str, path) -> Any:
        from pathlib import Path
        path = Path(path)
        e = self._entry
        timeout = float(e.get("request_timeout_s", DEFAULT_REQUEST_TIMEOUT_S))

        data: dict[str, Any] = {"text": text}
        # Mirrors upstream SynthesizeVoice.to_dict(): name wins, speaker
        # rides along; otherwise a bare language.
        voice: dict[str, Any] = {}
        if e.get("voice_name"):
            voice["name"] = e["voice_name"]
            if e.get("voice_speaker"):
                voice["speaker"] = e["voice_speaker"]
        elif e.get("language"):
            voice["language"] = e["language"]
        if voice:
            data["voice"] = voice

        conn = self._new_connection()
        conn.connect(timeout=float(e.get("connect_timeout_s",
                                         DEFAULT_CONNECT_TIMEOUT_S)))
        try:
            write_event(conn.sock, "synthesize", data)
            rate: int | None = None
            chunks: list[bytes] = []
            while True:
                ev = self._read_until(
                    conn, {"audio-start", "audio-chunk", "audio-stop"}, timeout)
                if ev.type == "audio-start":
                    rate = int(ev.data["rate"])
                    width = int(ev.data.get("width", 2))
                    channels = int(ev.data.get("channels", 1))
                    if width != 2 or channels != 1:
                        raise WyomingProtocolError(
                            f"[{e['name']}] unsupported TTS audio format: "
                            f"{width * 8}-bit x{channels} "
                            f"(only 16-bit mono is supported)")
                elif ev.type == "audio-chunk":
                    if ev.payload:
                        chunks.append(ev.payload)
                else:  # audio-stop
                    break
            if rate is None:
                raise WyomingProtocolError(
                    f"[{e['name']}] TTS stream ended without audio-start")
            samples = np.frombuffer(b"".join(chunks), dtype=np.int16)
            _p.write_wav_pcm16(path, samples, rate)
            return path
        finally:
            conn.close()


class WyomingWakeWord(WyomingAdapter, WakeWordProvider):
    """Wake-word slot backed by a Wyoming wake server (e.g. wyoming-openwakeword).

    Flow: `detect` (+ optional names) → audio-start/chunk/stop →
    `detection` or `not-detected`. Upstream Detection carries no
    confidence score, so this returns 1.0 on detection and 0.0
    otherwise — callers must not treat the score as calibrated.
    """

    def detect(self, samples: np.ndarray) -> tuple[bool, str, float]:
        e = self._entry
        timeout = float(e.get("request_timeout_s", DEFAULT_REQUEST_TIMEOUT_S))
        pcm = self._pcm16_bytes(samples)

        names = list(e.get("phrase_names") or [])
        # Upstream Detect sends {"names": None} for "any model".
        data: dict[str, Any] = {"names": names or None}

        conn = self._new_connection()
        conn.connect(timeout=float(e.get("connect_timeout_s",
                                         DEFAULT_CONNECT_TIMEOUT_S)))
        try:
            write_event(conn.sock, "detect", data)
            self._send_audio_stream(conn, pcm)
            ev = self._read_until(conn, {"detection", "not-detected"}, timeout)
            if ev.type == "detection":
                return True, str(ev.data.get("name") or ""), 1.0
            return False, "", 0.0
        finally:
            conn.close()


# ── Factory ──────────────────────────────────────────────────────────

_SLOT_BASES: dict[SlotType, type] = {
    SlotType.STT: WyomingSTT,
    SlotType.TTS: WyomingTTS,
    SlotType.WAKE_WORD: WyomingWakeWord,
}

# Slots servable over Wyoming TCP. The protocol also defines VAD events
# (voice-started/voice-stopped) but no per-chunk VAD query exists, so
# the VAD slot stays subprocess-only for now.
TCP_SUPPORTED_SLOTS = frozenset(_SLOT_BASES)


def make_wyoming_provider(entry: dict[str, Any]) -> type:
    """Build a concrete Wyoming* provider class for a config entry.

    *entry* is the normalized dict from ``echo_node.adapters``:
    ``name``, ``slot`` (value string), ``slot_enum``, ``transport``,
    ``host``, ``port``, timeouts, optional model/language/voice/phrase
    hints, ``label``, ``experimental``, ``capabilities``.
    """
    slot = entry["slot_enum"]
    base = _SLOT_BASES.get(slot)
    if base is None:
        raise ValueError(
            f"wyoming provider {entry['name']!r}: slot {slot.value!r} cannot "
            f"be served over Wyoming TCP (supported: "
            f"{sorted(s.value for s in TCP_SUPPORTED_SLOTS)})")
    safe = "".join(c if (c.isalnum() or c in "_-") else "_" for c in entry["name"])
    cls_name = f"Wyoming{safe.title().replace('_', '').replace('-', '')}"
    attrs: dict[str, Any] = {
        "_entry": dict(entry),
        "label": str(entry.get("label") or entry["name"]),
        "__doc__": (f"Wyoming TCP {slot.value} provider {entry['name']!r} "
                    f"({entry['host']}:{entry['port']}, declared in config.yaml)."),
        "__module__": __name__,
    }
    return type(cls_name, (base,), attrs)


__all__ = [
    "WyomingAdapter",
    "WyomingSTT",
    "WyomingTTS",
    "WyomingWakeWord",
    "WyomingEvent",
    "WyomingError",
    "WyomingConnectionError",
    "WyomingProtocolError",
    "WyomingConnection",
    "write_event",
    "read_event",
    "make_wyoming_provider",
    "TCP_SUPPORTED_SLOTS",
    "CONVENTIONAL_PORTS",
    "CLIENT_VERSION",
]
