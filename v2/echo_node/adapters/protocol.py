"""JSON-RPC 2.0 over stdio: shared framing for the Echo-Node subprocess
adapter protocol (Phase B of ROADMAP.md).

Both the host side (``echo_node.adapters.subprocess_adapter``) and the
adapter scripts (``echo_node/adapters/*.py``) import this module, so the
framing is defined exactly once.

Wire format: newline-delimited JSON — one JSON-RPC 2.0 object per line on
stdout (host reads the child's stdout; the child reads its stdin). The
child's stderr is log-only and is never parsed.

Methods (all batch-only in Phase B — no streaming):

    initialize  -> {protocol_version, slot, name, capabilities}
    validate    -> {ok, reason, details}            (child's self-probe)
    ping        -> {ok: true}                       (liveness)
    shutdown    -> {ok: true}                       (child exits after replying)
    transcribe  {pcm_b64, sample_rate} -> {text}                    [stt]
    synthesize  {text} -> {pcm_b64, sample_rate}                    [tts]
    is_speech   {pcm_b64, sample_rate} -> {speech, score}           [vad]
    detect      {pcm_b64, sample_rate} -> {detected, phrase, score} [wake_word]
    chat        {text, system} -> {text}                           [agent_backend]

PCM payloads are base64-encoded little-endian int16 mono. The host
normalizes STT/VAD/wake-word input to 16 kHz mono; TTS children report
their own sample rate in the response.
"""

from __future__ import annotations

import base64
import io
import json
import sys
import wave
from typing import Any, Callable

import numpy as np

# NOTE: no `echo_node` import at module top. This module must stay
# importable by adapter child processes that only have the adapters/
# directory on sys.path (no v2/ root). The typed Capability helpers
# below import it lazily; children should just build plain dicts.

PROTOCOL_VERSION = 1


# ── Errors ──────────────────────────────────────────────────────────

class ProtocolError(Exception):
    """Base class for everything that can go wrong on the wire."""


class AdapterTimeout(ProtocolError):
    """The child did not answer within the request timeout."""


class AdapterCrashed(ProtocolError):
    """The child process died (and restarts are exhausted)."""


class AdapterError(ProtocolError):
    """The child answered with a JSON-RPC error object."""

    def __init__(self, code: int, message: str):
        super().__init__(f"adapter error {code}: {message}")
        self.code = code
        self.message = message


# ── Framing ─────────────────────────────────────────────────────────

def encode_request(method: str, params: dict[str, Any] | None = None,
                   request_id: int = 0) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": request_id,
                       "method": method, "params": params or {}})


def encode_response(request_id: Any, result: Any) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result})


def encode_error(request_id: Any, code: int, message: str) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": request_id,
                       "error": {"code": code, "message": message}})


def decode_message(line: str) -> dict[str, Any]:
    """Parse one wire line. Raises ProtocolError on malformed input."""
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"not JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise ProtocolError(f"message is not an object: {line[:80]!r}")
    return obj


def check_request(msg: dict[str, Any]) -> tuple[Any, str, dict[str, Any]]:
    """Validate a JSON-RPC 2.0 request. Returns (id, method, params)."""
    if msg.get("jsonrpc") != "2.0":
        raise ProtocolError("missing/invalid 'jsonrpc': must be '2.0'")
    method = msg.get("method")
    if not isinstance(method, str) or not method:
        raise ProtocolError("missing 'method'")
    if "id" not in msg:
        raise ProtocolError("missing 'id'")
    params = msg.get("params") or {}
    if not isinstance(params, dict):
        raise ProtocolError("'params' must be an object")
    return msg["id"], method, params


def write_message(stream: Any, text: str) -> None:
    stream.write(text + "\n")
    stream.flush()


# ── Child-side main loop ────────────────────────────────────────────

def run_adapter(handler: Any) -> int:
    """Run the adapter request loop on stdin/stdout. Never raises.

    *handler* exposes ``rpc_<method>(params) -> result`` methods.
    ``rpc_shutdown`` is answered, then the loop exits with code 0.
    """
    stdin, stdout = sys.stdin, sys.stdout
    for raw in stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = decode_message(line)
            request_id, method, params = check_request(msg)
        except ProtocolError as exc:
            write_message(stdout, encode_error(None, -32700, f"parse error: {exc}"))
            continue
        fn: Callable[[dict[str, Any]], Any] | None = getattr(
            handler, "rpc_" + method, None)
        if fn is None:
            write_message(stdout, encode_error(request_id, -32601,
                                               f"unknown method {method!r}"))
            continue
        try:
            result = fn(params)
        except AdapterError as exc:  # adapter's own domain errors
            write_message(stdout, encode_error(request_id, exc.code, exc.message))
            continue
        except Exception as exc:  # never let one bad call kill the loop
            write_message(stdout, encode_error(request_id, -32603,
                                               f"{type(exc).__name__}: {exc}"))
            continue
        if result is None:
            result = {}
        write_message(stdout, encode_response(request_id, result))
        if method == "shutdown":
            return 0
    return 0


# ── Capability dict conversion ──────────────────────────────────────

_CAPABILITY_FIELDS = ("name", "version", "languages", "streaming", "vram_gb",
                      "gpu_required", "license", "network", "notes")


def capability_to_dict(cap: "Capability") -> dict[str, Any]:
    """Host-side helper: typed Capability -> wire dict.

    Adapter children should build the dict literally instead (see the
    reference adapters) so they never need the echo_node package.
    """
    return {f: getattr(cap, f) for f in _CAPABILITY_FIELDS}


def capability_from_dict(d: dict[str, Any]) -> "Capability":
    from echo_node.slots import Capability
    kwargs = {f: d[f] for f in _CAPABILITY_FIELDS if f in d}
    return Capability(**kwargs)


# ── PCM helpers ─────────────────────────────────────────────────────

def pcm16_to_b64(samples: np.ndarray) -> str:
    arr = np.asarray(samples, dtype=np.int16).ravel()
    return base64.b64encode(arr.tobytes()).decode("ascii")


def b64_to_pcm16(payload: str) -> np.ndarray:
    raw = base64.b64decode(payload.encode("ascii"))
    return np.frombuffer(raw, dtype=np.int16).copy()


def read_wav_pcm16(path: Any, target_rate: int = 16000) -> tuple[np.ndarray, int]:
    """Read a WAV file, normalizing to mono int16 at *target_rate*.

    Uses only the stdlib ``wave`` module plus numpy for conversion —
    no audio dependencies required on either side of the pipe.
    """
    with wave.open(str(path), "rb") as w:
        n_channels = w.getnchannels()
        sampwidth = w.getsampwidth()
        rate = w.getframerate()
        frames = w.readframes(w.getnframes())
    if sampwidth == 1:
        arr = (np.frombuffer(frames, dtype=np.uint8).astype(np.int32) - 128) * 256
    elif sampwidth == 2:
        arr = np.frombuffer(frames, dtype=np.int16).astype(np.int32)
    elif sampwidth == 4:
        arr = (np.frombuffer(frames, dtype=np.int32) >> 16).astype(np.int32)
    else:
        raise ProtocolError(f"unsupported WAV sample width: {sampwidth}")
    if n_channels > 1:
        arr = arr.reshape(-1, n_channels).mean(axis=1).astype(np.int32)
    arr = np.clip(arr, -32768, 32767).astype(np.int16)
    if rate != target_rate and len(arr) > 1:
        # Naive linear resample — fine for a transport normalization step.
        src_x = np.linspace(0.0, 1.0, len(arr))
        dst_x = np.linspace(0.0, 1.0, int(len(arr) * target_rate / rate))
        arr = np.interp(dst_x, src_x, arr.astype(np.float64)).astype(np.int16)
        rate = target_rate
    return arr, rate


def write_wav_pcm16(path: Any, samples: np.ndarray, sample_rate: int) -> None:
    """Write mono int16 PCM to a WAV file (stdlib only)."""
    arr = np.asarray(samples, dtype=np.int16).ravel()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sample_rate))
        w.writeframes(arr.tobytes())
    with open(path, "wb") as f:
        f.write(buf.getvalue())


__all__ = [
    "PROTOCOL_VERSION",
    "ProtocolError", "AdapterTimeout", "AdapterCrashed", "AdapterError",
    "encode_request", "encode_response", "encode_error",
    "decode_message", "check_request", "write_message",
    "run_adapter",
    "capability_to_dict", "capability_from_dict",
    "pcm16_to_b64", "b64_to_pcm16", "read_wav_pcm16", "write_wav_pcm16",
]
