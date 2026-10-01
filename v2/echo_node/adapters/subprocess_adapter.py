"""Host side of the Phase B subprocess adapter protocol.

:class:`_SubprocessHandle` owns one child process: lazy spawn, the
``initialize`` handshake with a protocol-version check, request/response
matching with per-call timeouts, restart on unexpected death, kill-on-idle
reaping, and stderr drained to the app log.

One public class per slot ABC — :class:`SubprocessSTT`,
:class:`SubprocessTTS`, :class:`SubprocessVAD`,
:class:`SubprocessWakeWord`, :class:`SubprocessAgentBackend` — shares the
handle. Concrete provider classes are built by
:func:`make_external_provider` in ``echo_node.adapters`` from a config
entry, so the registry keeps working with plain classes (no API change
from Phase A).
"""

from __future__ import annotations

import itertools
import logging
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np

from echo_node import backends as _backends
from echo_node.adapters import protocol as _p
from echo_node.adapters.protocol import (
    AdapterCrashed,
    AdapterError,
    AdapterTimeout,
    ProtocolError,
)
from echo_node.slots import (
    Capability,
    SlotType,
    STTProvider,
    TTSProvider,
    VADProvider,
    WakeWordProvider,
)
from echo_node.slots.validation import ValidationResult, missing_result, ok_result

log = logging.getLogger("echo_node.adapters")

_EOF = object()  # sentinel: child stdout hit EOF (child died mid-call)


# ── Process handle ──────────────────────────────────────────────────

class _SubprocessHandle:
    """Owns the lifecycle of one adapter child process."""

    def __init__(
        self,
        argv: list[str],
        *,
        name: str = "adapter",
        request_timeout_s: float = 30.0,
        idle_timeout_s: float = 120.0,
        max_restarts: int = 3,
    ) -> None:
        if not argv:
            raise ValueError("adapter argv must be non-empty")
        self.argv = list(argv)
        self.name = name
        self.request_timeout_s = float(request_timeout_s)
        self.idle_timeout_s = float(idle_timeout_s)
        self.max_restarts = int(max_restarts)
        self._lock = threading.Lock()
        self._pending_lock = threading.Lock()
        self._pending: dict[int, queue.Queue] = {}
        self._ids = itertools.count(1)
        self._proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._reaper: threading.Thread | None = None
        self._reaper_stop = threading.Event()
        self._restarts = 0
        # True once a child has been spawned and not yet deliberately shut
        # down (close() / idle-reap). Lets _ensure_alive() tell an
        # unexpected death (count it against max_restarts) from a fresh
        # start or an intentional teardown (don't count).
        self._ever_spawned = False
        self._last_used = 0.0
        self.remote_info: dict[str, Any] = {}

    # ── spawn / handshake ───────────────────────────────────────

    def _spawn(self) -> None:
        log.info(f"[{self.name}] spawning: {' '.join(self.argv)}")
        try:
            proc = subprocess.Popen(
                self.argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # line-buffered: one JSON object per line
            )
        except FileNotFoundError as exc:
            raise AdapterCrashed(f"[{self.name}] cannot start {self.argv[0]!r}: {exc}") from exc
        except OSError as exc:
            raise AdapterCrashed(f"[{self.name}] failed to spawn: {exc}") from exc
        self._proc = proc
        self._last_used = time.time()
        self._ever_spawned = True
        self._reader = threading.Thread(target=self._reader_loop,
                                        name=f"adapter-{self.name}-reader",
                                        daemon=True)
        self._reader.start()
        self._stderr_thread = threading.Thread(target=self._stderr_loop,
                                               name=f"adapter-{self.name}-stderr",
                                               daemon=True)
        self._stderr_thread.start()
        if self._reaper is None:
            self._reaper_stop.clear()
            self._reaper = threading.Thread(target=self._reaper_loop,
                                            name=f"adapter-{self.name}-reaper",
                                            daemon=True)
            self._reaper.start()

    def _do_handshake(self) -> dict[str, Any]:
        result = self._raw_call("initialize", {}, timeout=self.request_timeout_s)
        try:
            version = int(result.get("protocol_version", 0))
        except (TypeError, ValueError):
            version = 0
        if version != _p.PROTOCOL_VERSION:
            raise AdapterError(-32600, f"protocol version mismatch: child reports "
                                      f"{result.get('protocol_version')!r}, host speaks "
                                      f"{_p.PROTOCOL_VERSION}")
        self.remote_info = dict(result)
        log.info(f"[{self.name}] handshake ok: slot={result.get('slot')} "
                 f"name={result.get('name')}")
        return self.remote_info

    def _ensure_alive(self) -> None:
        """Spawn on first use; restart after unexpected death.

        Every unexpected death is counted against max_restarts exactly
        once — including deaths observed mid-call (call() reaps the proc
        so poll() is set before coming back here) and deaths during the
        handshake. Intentional teardowns (close(), idle-reap) reset
        _ever_spawned, so the next spawn starts fresh.
        """
        proc = self._proc
        if proc is not None and proc.poll() is None:
            return
        if self._ever_spawned:
            self._restarts += 1
            log.warning(f"[{self.name}] child died unexpectedly; "
                        f"restart {self._restarts}/{self.max_restarts}")
            if self._restarts > self.max_restarts:
                raise AdapterCrashed(
                    f"[{self.name}] child died {self._restarts} times "
                    f"(max {self.max_restarts}) — not restarting. "
                    f"Check the adapter's stderr in the app log.")
            self._fail_pending(_EOF)
        self._spawn()
        try:
            self._do_handshake()
        except Exception:
            self._kill_proc()
            self._proc = None
            raise

    # ── request/response ────────────────────────────────────────

    def _raw_call(self, method: str, params: dict[str, Any] | None,
                  timeout: float | None = None) -> Any:
        """Single attempt: no restart, no handshake. Returns result payload."""
        proc = self._proc
        assert proc is not None and proc.stdin is not None
        request_id = next(self._ids)
        fut: queue.Queue = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._pending[request_id] = fut
        try:
            _p.write_message(proc.stdin, _p.encode_request(method, params, request_id))
        except (BrokenPipeError, OSError):
            with self._pending_lock:
                self._pending.pop(request_id, None)
            self._fail_pending(_EOF)
            raise AdapterCrashed(f"[{self.name}] child stdin broken (child died)")
        self._last_used = time.time()
        try:
            resp = fut.get(timeout=timeout if timeout is not None
                           else self.request_timeout_s)
        except queue.Empty:
            raise AdapterTimeout(
                f"[{self.name}] no response to {method!r} within "
                f"{timeout or self.request_timeout_s:.0f}s")
        finally:
            with self._pending_lock:
                self._pending.pop(request_id, None)
        if resp is _EOF:
            raise AdapterCrashed(f"[{self.name}] child died during {method!r}")
        if isinstance(resp, dict) and "error" in resp:
            err = resp["error"] or {}
            raise AdapterError(int(err.get("code", -32603)),
                               str(err.get("message", "unknown error")))
        if not isinstance(resp, dict) or "result" not in resp:
            raise ProtocolError(f"[{self.name}] malformed response to {method!r}")
        return resp["result"]

    def call(self, method: str, params: dict[str, Any] | None = None,
             timeout: float | None = None) -> Any:
        """Call the child, restarting it once if it died mid-call."""
        with self._lock:
            self._ensure_alive()
            try:
                return self._raw_call(method, params, timeout)
            except AdapterCrashed:
                # One restart-and-retry. _kill_proc() reaps the dead proc
                # (so poll() is set); _ensure_alive() counts the death
                # against max_restarts. _proc is deliberately NOT nulled —
                # nulling it would skip the counting.
                self._kill_proc()
                self._ensure_alive()
                return self._raw_call(method, params, timeout)

    def ping(self, timeout: float = 5.0) -> bool:
        try:
            self.call("ping", {}, timeout=timeout)
            return True
        except ProtocolError:
            return False

    # ── reader / stderr / reaper threads ─────────────────────────

    def _reader_loop(self) -> None:
        proc = self._proc
        assert proc is not None and proc.stdout is not None
        try:
            for raw in proc.stdout:
                line = raw.strip()
                if not line:
                    continue
                try:
                    msg = _p.decode_message(line)
                except ProtocolError as exc:
                    # Malformed line from the child: log and keep going —
                    # never let garbage poison the request/response stream.
                    log.warning(f"[{self.name}] ignoring malformed child output: {exc}")
                    continue
                request_id = msg.get("id")
                with self._pending_lock:
                    fut = self._pending.get(request_id)
                if fut is not None:
                    fut.put(msg)
                else:
                    log.debug(f"[{self.name}] unsolicited child message: {line[:120]}")
        finally:
            # EOF: the child is gone — fail everything still waiting.
            self._fail_pending(_EOF)

    def _fail_pending(self, sentinel: Any) -> None:
        with self._pending_lock:
            pending = list(self._pending.values())
            self._pending.clear()
        for fut in pending:
            try:
                fut.put_nowait(sentinel)
            except queue.Full:
                pass

    def _stderr_loop(self) -> None:
        proc = self._proc
        assert proc is not None and proc.stderr is not None
        try:
            for raw in proc.stderr:
                line = raw.rstrip()
                if line:
                    log.debug(f"[{self.name} stderr] {line}")
        except Exception:
            pass

    def _reaper_loop(self) -> None:
        """Kill-on-idle: reap the child after idle_timeout_s of no calls."""
        while not self._reaper_stop.wait(timeout=min(30.0, max(5.0, self.idle_timeout_s / 2))):
            proc = self._proc
            if proc is None or proc.poll() is not None:
                continue
            idle_for = time.time() - self._last_used
            if idle_for >= self.idle_timeout_s:
                log.info(f"[{self.name}] idle for {idle_for:.0f}s "
                         f"(>{self.idle_timeout_s:.0f}s) — reaping child")
                with self._lock:
                    # Re-check under the lock; a call may have started.
                    if time.time() - self._last_used >= self.idle_timeout_s:
                        self._kill_proc()
                        self._proc = None
                        # Intentional teardown, not a crash: the next
                        # spawn starts with a clean restart budget.
                        self._ever_spawned = False

    def _kill_proc(self) -> None:
        proc = self._proc
        if proc is None:
            return
        try:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        except Exception:
            pass

    # ── shutdown ────────────────────────────────────────────────

    def close(self) -> None:
        """Ask the child to exit cleanly, then make sure it's gone."""
        with self._lock:
            proc = self._proc
            if proc is not None and proc.poll() is None:
                try:
                    self._raw_call("shutdown", {}, timeout=5)
                except ProtocolError:
                    pass
                self._kill_proc()
            self._proc = None
            self._ever_spawned = False  # deliberate shutdown, not a crash
            self._fail_pending(_EOF)
            self._reaper_stop.set()

    def __enter__(self) -> "_SubprocessHandle":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


# ── External provider base ──────────────────────────────────────────

_CAPABILITY_FIELD_NAMES = ("name", "version", "languages", "streaming",
                           "vram_gb", "gpu_required", "license", "network", "notes")


class _ExternalBase:
    """Shared behavior for all subprocess-backed providers.

    Concrete classes are built by :func:`make_external_provider`, which
    binds the config *entry* as the ``_entry`` class attribute:

        entry = {"name": ..., "slot": "stt", "argv": [...],
                 "request_timeout_s": 30.0, "idle_timeout_s": 120.0,
                 "max_restarts": 3, "label": ..., "capabilities": {...}}
    """

    _entry: dict[str, Any] = {}

    def __init__(self, config: dict[str, Any]):
        self.config = dict(config)
        self._handle: _SubprocessHandle | None = None

    # ── handle ──

    def _h(self) -> _SubprocessHandle:
        if self._handle is None:
            e = self._entry
            self._handle = _SubprocessHandle(
                e["argv"],
                name=e["name"],
                request_timeout_s=e.get("request_timeout_s", 30.0),
                idle_timeout_s=e.get("idle_timeout_s", 120.0),
                max_restarts=e.get("max_restarts", 3),
            )
        return self._handle

    def _close_handle(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    # ── slot contract: capabilities + validate ──

    @classmethod
    def capabilities(cls) -> Capability:
        e = cls._entry
        override = {k: v for k, v in (e.get("capabilities") or {}).items()
                    if k in _CAPABILITY_FIELD_NAMES}
        argv0 = e["argv"][0] if e.get("argv") else "?"
        return Capability(
            name=e.get("name", cls.__name__),
            notes=f"external subprocess provider ({argv0}); "
                  f"declared in config.yaml, never in the settings UI",
            **override,
        )

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        e = cls._entry
        exe = e["argv"][0]
        # Host-side pre-check: is the executable even there?
        if not (os.path.isabs(exe) and Path(exe).exists()) and not shutil.which(exe):
            return missing_result(f"executable {exe!r} for external provider {e['name']!r}",
                                  {"executable": exe})
        handle = _SubprocessHandle(
            e["argv"],
            name=e["name"],
            request_timeout_s=e.get("request_timeout_s", 30.0),
            idle_timeout_s=e.get("idle_timeout_s", 120.0),
            max_restarts=0,  # validation gets one clean attempt
        )
        try:
            try:
                handle._ensure_alive()
                info = handle.remote_info
            except ProtocolError as exc:
                return ValidationResult(False, f"adapter would not start: {exc}",
                                        {"executable": exe})
            child_slot = str(info.get("slot", ""))
            if child_slot and child_slot != e["slot"]:
                return ValidationResult(False,
                                        f"adapter reports slot {child_slot!r} but config "
                                        f"declares {e['slot']!r}", {})
            # Child self-probe.
            try:
                child = handle.call("validate", {}, timeout=15)
            except ProtocolError as exc:
                return ValidationResult(False, f"adapter self-probe failed: {exc}", {})
            if not isinstance(child, dict) or not child.get("ok"):
                reason = child.get("reason", "no reason given") if isinstance(child, dict) else repr(child)
                return ValidationResult(False, f"adapter self-check failed: {reason}", {})
            # Host-side smoke check: a ping round-trip through the same pipe.
            if not handle.ping(timeout=5):
                return ValidationResult(False, "adapter ping round-trip failed", {})
            return ok_result(f"external {e['name']}: {child.get('reason', 'self-check passed')}",
                             {"child_reason": child.get("reason", ""),
                              "remote_name": info.get("name", "")})
        finally:
            handle.close()

    # ── helpers for slot methods ──

    def _call(self, method: str, params: dict[str, Any] | None = None,
              timeout: float | None = None) -> Any:
        return self._h().call(method, params, timeout)

    @staticmethod
    def _pcm_params(samples: np.ndarray) -> dict[str, Any]:
        """Mic chunk -> wire params. The wire is 16 kHz mono int16
        (the pipeline's mic chunks already are); float input is scaled,
        anything else is cast."""
        a = np.asarray(samples)
        if a.dtype.kind == "f":
            a = np.clip(a, -1.0, 1.0) * 32767.0
        a = np.asarray(a, dtype=np.int16).ravel()
        return {"pcm_b64": _p.pcm16_to_b64(a), "sample_rate": 16000}


# ── Per-slot adapter classes ─────────────────────────────────────────

class SubprocessSTT(_ExternalBase, STTProvider):
    """STT slot backed by an external program over the adapter protocol."""

    def load(self) -> None:
        self._h()._ensure_alive()

    def unload(self) -> None:
        self._close_handle()

    def transcribe(self, wav_path: Path) -> str:
        samples, _rate = _p.read_wav_pcm16(wav_path, target_rate=16000)
        result = self._call("transcribe", self._pcm_params(samples))
        if not isinstance(result, dict):
            raise ProtocolError(f"[{self._entry['name']}] bad transcribe response")
        return str(result.get("text", "")).strip()


class SubprocessTTS(_ExternalBase, TTSProvider):
    """TTS slot backed by an external program over the adapter protocol."""

    def load(self) -> None:
        self._h()._ensure_alive()

    def unload(self) -> None:
        self._close_handle()

    def warm(self) -> None:
        if not self._h().ping(timeout=10):
            raise ProtocolError(f"[{self._entry['name']}] warm ping failed")

    def synthesize_to_wav(self, text: str, path: Path) -> Path:
        result = self._call("synthesize", {"text": text})
        if not isinstance(result, dict) or "pcm_b64" not in result:
            raise ProtocolError(f"[{self._entry['name']}] bad synthesize response")
        samples = _p.b64_to_pcm16(str(result["pcm_b64"]))
        rate = int(result.get("sample_rate", 16000))
        _p.write_wav_pcm16(path, samples, rate)
        return path


class SubprocessVAD(_ExternalBase, VADProvider):
    """VAD slot backed by an external program over the adapter protocol."""

    def _probe(self, samples: np.ndarray) -> dict[str, Any]:
        result = self._call("is_speech", self._pcm_params(samples))
        if not isinstance(result, dict):
            raise ProtocolError(f"[{self._entry['name']}] bad is_speech response")
        return result

    def score(self, samples: np.ndarray) -> float:
        return float(self._probe(samples).get("score", 0.0))

    def is_speech(self, samples: np.ndarray) -> bool:
        return bool(self._probe(samples).get("speech", False))


class SubprocessWakeWord(_ExternalBase, WakeWordProvider):
    """Wake-word slot backed by an external program over the adapter protocol."""

    def detect(self, samples: np.ndarray) -> tuple[bool, str, float]:
        result = self._call("detect", self._pcm_params(samples))
        if not isinstance(result, dict):
            raise ProtocolError(f"[{self._entry['name']}] bad detect response")
        return (bool(result.get("detected", False)),
                str(result.get("phrase", "")),
                float(result.get("score", 0.0)))


class SubprocessAgentBackend(_ExternalBase, _backends.AgentBackend):
    """AgentBackend slot backed by an external program over the adapter protocol."""

    # `name` / `config_key` are set by make_external_provider per entry.

    def is_available(self) -> bool:
        try:
            return self._h().ping(timeout=5)
        except Exception:
            return False

    def chat(self, text: str, system: str = "") -> str:
        result = self._call("chat", {"text": text, "system": system or ""})
        if not isinstance(result, dict):
            raise ProtocolError(f"[{self._entry['name']}] bad chat response")
        return str(result.get("text", ""))


# ── Factory ──────────────────────────────────────────────────────────

_SLOT_BASES: dict[SlotType, type] = {
    SlotType.STT: SubprocessSTT,
    SlotType.TTS: SubprocessTTS,
    SlotType.VAD: SubprocessVAD,
    SlotType.WAKE_WORD: SubprocessWakeWord,
    SlotType.AGENT_BACKEND: SubprocessAgentBackend,
}

# Slots the Phase B protocol covers. Avatar, audio I/O and barge-in are
# not batch request/response shaped (or need hardware), so external
# programs cannot take those slots yet — Phase D territory.
SUPPORTED_SLOTS = frozenset(_SLOT_BASES)


def make_external_provider(entry: dict[str, Any]) -> type:
    """Build a concrete Subprocess* provider class for a config entry.

    *entry* is the normalized dict from ``echo_node.adapters``:
    ``name``, ``slot`` (value string), ``slot_enum``, ``argv``,
    timeouts, ``label``, ``experimental``, ``capabilities``.
    """
    slot = entry["slot_enum"]
    base = _SLOT_BASES.get(slot)
    if base is None:
        raise ValueError(
            f"external provider {entry['name']!r}: slot {slot.value!r} cannot be "
            f"served by a subprocess adapter in Phase B (supported: "
            f"{sorted(s.value for s in SUPPORTED_SLOTS)})")
    safe = "".join(c if (c.isalnum() or c in "_-") else "_" for c in entry["name"])
    cls_name = f"External{safe.title().replace('_', '').replace('-', '')}"
    attrs: dict[str, Any] = {
        "_entry": dict(entry),
        "label": str(entry.get("label") or entry["name"]),
        "__doc__": (f"External {slot.value} provider {entry['name']!r} "
                    f"(subprocess adapter, declared in config.yaml)."),
        "__module__": __name__,
    }
    if issubclass(base, _backends.AgentBackend):
        attrs["name"] = str(entry.get("label") or entry["name"])
        attrs["config_key"] = entry["name"]
    return type(cls_name, (base,), attrs)


__all__ = [
    "SubprocessSTT", "SubprocessTTS", "SubprocessVAD",
    "SubprocessWakeWord", "SubprocessAgentBackend",
    "make_external_provider", "SUPPORTED_SLOTS",
    "_SubprocessHandle",
]
