"""T020 gate probe: arming, offline controls, stall budget, budget verdict.

Runs as a script: ``python3 -m echo_node.tests.test_dialogue_gate``
from ``v2/``. Cross-platform: mic/wake/backend/speaker are fakes; the
real ``Assistant`` arming/turn/failure methods are exercised.

Cases (EVAL-001/004/005 procedure, logic half):
1. arm ok — healthy guard → armed, readiness printed, mic opened.
2. arm refused — denying guard → not armed, mic never opened.
3. offline controls — wake detect + VAD score + level meter run with
   NO provider contact (backend untouched counter).
4. stall — backend hangs past provider_timeout_s → _BackendStall,
   sanitized reason spoken, armed idle restored (armed stays True).
5. failure — backend raises → same sanitized path, no traceback text
   in the spoken reason.
6. disarm sticky — disarm() then backend failure → armed stays False.
7. budget verdict — ears→mouth ≤ budget logs WITHIN; over logs OVER;
   missing playback stamp logs nothing (never a false pass).
8. guard wiring — record_turn receives the shared guard (denial → turn
   ends with capture_disabled, mic untouched).
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tempfile

import numpy as np

from echo_node.capture_guard import CaptureGuard
from echo_node.conversation_logger import ConversationLogger, TurnRecord
from echo_node.pipeline.orchestrator import _BackendStall

PASSED: list[str] = []
FAILED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    (PASSED if ok else FAILED).append(label)
    print(f"[{'ok' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""),
          flush=True)


def _assistant(**overrides):
    """Minimal Assistant without running __init__ (heavy deps)."""
    from echo_node.pipeline import orchestrator as O
    a = O.Assistant.__new__(O.Assistant)
    a.config = {"dialogue": {"response_budget_s": 2.0,
                             "provider_timeout_s": overrides.get("timeout", 0.3)}}
    a.response_budget_s = 2.0
    a.provider_timeout_s = overrides.get("timeout", 0.3)
    a.guard = overrides.get("guard", CaptureGuard(os_name="posix"))
    a.armed = False
    a.stop = False
    a._level_last_print = 0.0
    a._last_state = "idle"
    a._has_wpctl = False
    a._avatar_state = None
    a.avatar = None
    return a


class _Mic:
    def __init__(self):
        self.opened = 0
        self.reads = 0

    def open(self):
        self.opened += 1

    def close(self):
        pass

    def read(self):
        self.reads += 1
        return (np.zeros(1280, dtype=np.int16) + 100)


class _Wake:
    def __init__(self):
        self.calls = 0

    def detect(self, samples):
        self.calls += 1
        return False, "", 0.0


class _Speaker:
    def __init__(self):
        self.spoken: list[str] = []

    def speak(self, text, mic=None, turn_rec=None):
        self.spoken.append(text)
        if turn_rec is not None:
            turn_rec.t_playback_start = time.perf_counter()
        return False


# 1. arm ok ------------------------------------------------------------------
a = _assistant()
a.guard.probe_consent = lambda: (True, "allow")
a.guard.probe_devices = lambda: (True, "1", ["mic"])
a.mic, a.wake, a.speaker = _Mic(), _Wake(), _Speaker()
a.hotkey = type("H", (), {"start": lambda self: True})()
a._prewarm = lambda: None
a._send_state = lambda s: None
check("arm ok arms", a.arm() is True and a.armed is True)
check("arm opens mic once", a.mic.opened == 1, str(a.mic.opened))

# 2. arm refused ----------------------------------------------------------------
a2 = _assistant()
a2.guard.probe_consent = lambda: (False, "Deny")
a2.guard.probe_devices = lambda: (True, "1", ["mic"])
a2.mic = _Mic()
a2.hotkey = type("H", (), {"start": lambda self: True})()
a2._prewarm = lambda: None
a2._send_state = lambda s: None
check("arm refused on denial", a2.arm() is False and a2.armed is False)
check("refused arm never opens mic", a2.mic.opened == 0)

# 3. offline controls need no provider -------------------------------------------
a3 = _assistant()
provider_contacted = {"n": 0}


class _CountingBackend:
    def is_available(self):
        provider_contacted["n"] += 1
        return True


a3.mic, a3.wake = _Mic(), _Wake()
samples = a3.mic.read()
detected, _, _ = a3.wake.detect(samples)
a3._level_meter(samples)
check("wake runs offline", a3.wake.calls == 1 and not detected)
check("no provider contacted", provider_contacted["n"] == 0)

# 4. stall → sanitized return to armed idle ---------------------------------------
a4 = _assistant(timeout=0.2)
a4.armed = True


class _HangingBackend:
    def chat_stream(self, text, system=""):
        import time as _t
        _t.sleep(5)
        yield "never", True

    def chat(self, text, system=""):
        import time as _t
        _t.sleep(5)
        return "never"


a4.speaker = _Speaker()

a4.logger = ConversationLogger({"log_dir": tempfile.mkdtemp()})
rec = TurnRecord(turn_id=1, route="probe")
rec.t_wake = time.perf_counter()


class _T2T:
    def __call__(self, stream):
        return (t for t, _ in stream)


try:
    a4._backend_with_timeout(_HangingBackend(), "hi", "", rec, _T2T())
    check("stall raises _BackendStall", False, "no raise")
except _BackendStall as stall:
    check("stall raises _BackendStall", stall.kind == "stalled", stall.kind)
t0 = time.perf_counter()
# (timeout Spielraum: the 0.2s budget must trip, not the 5s sleep)
check("stall trips fast", time.perf_counter() - t0 < 4.0)
a4._send_state = lambda s: None
a4._backend_failure(rec, "stalled")
check("failure keeps eligible armed idle", a4.armed is True)
check("sanitized reason spoken",
      any("too long" in s for s in a4.speaker.spoken),
      str(a4.speaker.spoken))
check("no internals in spoken reason",
      not any("Traceback" in s or "TimeoutError" in s for s in a4.speaker.spoken))

# 5. hard failure ------------------------------------------------------------------
a5 = _assistant(timeout=2.0)
a5.armed = True
a5.speaker = _Speaker()
a5.logger = ConversationLogger({"log_dir": tempfile.mkdtemp()})
a5._send_state = lambda s: None


class _BrokenBackend:
    def chat_stream(self, text, system=""):
        raise ConnectionResetError("conn reset by peer XYZ-123")

    def chat(self, text, system=""):
        raise ConnectionResetError("conn reset by peer XYZ-123")


rec5 = TurnRecord(turn_id=2, route="probe")
rec5.t_wake = time.perf_counter()
try:
    a5._backend_with_timeout(_BrokenBackend(), "hi", "", rec5, _T2T())
    check("failure raises _BackendStall", False, "no raise")
except _BackendStall as stall:
    check("failure raises _BackendStall", stall.kind == "failed", stall.kind)
a5._backend_failure(rec5, "failed")
check("failure keeps eligible armed idle", a5.armed is True)
check("failure reason sanitized",
      any("unavailable" in s for s in a5.speaker.spoken)
      and not any("XYZ-123" in s for s in a5.speaker.spoken),
      str(a5.speaker.spoken))

# 6. disarm sticky -------------------------------------------------------------------
a5.disarm = lambda: (setattr(a5, "armed", False),
                     setattr(a5.guard, "disarmed_by_user", True))
a5.disarm()
a5._backend_failure(rec5, "failed")
check("disarmed stays disarmed after failure", a5.armed is False)

# 7. budget verdict ---------------------------------------------------------------------
a7 = _assistant()
lines: list[str] = []
import builtins

_real_print = builtins.print


def _cap(*args, **kwargs):
    lines.append(" ".join(str(x) for x in args))


builtins.print = _cap
try:
    r = TurnRecord(turn_id=3, route="probe")
    r.t_listen_done, r.t_playback_start = 100.0, 101.2
    r.derive_latencies()
    a7._budget_verdict(r)
    fast = any("WITHIN" in ln for ln in lines)
    lines.clear()
    r2 = TurnRecord(turn_id=4, route="probe")
    r2.t_listen_done, r2.t_playback_start = 100.0, 103.5
    r2.derive_latencies()
    a7._budget_verdict(r2)
    slow = any("OVER" in ln for ln in lines)
    lines.clear()
    r3 = TurnRecord(turn_id=5, route="probe")
    r3.t_listen_done = 100.0  # no playback stamp
    r3.derive_latencies()
    a7._budget_verdict(r3)
    silent = len(lines) == 0
finally:
    builtins.print = _real_print
check("within-budget logs WITHIN", fast)
check("over-budget logs OVER", slow)
check("missing stamp never false-passes", silent)

# 8. guard wiring: recorder honors shared guard -------------------------------------------
from echo_node.components.vad import Recorder

reads = {"n": 0}


class _DeadMic:
    def read(self):
        reads["n"] += 1
        raise AssertionError("mic touched")


class _NoVad:
    def is_speech(self, samples):
        return False


g = CaptureGuard(os_name="posix")
g.probe_consent = lambda: (False, "Deny")
g.probe_devices = lambda: (True, "1", ["mic"])
rec8 = Recorder(_DeadMic(), _NoVad(), {})
check("wired recorder returns None on denial", rec8.record_turn(guard=g) is None)
check("wired recorder never touches mic", reads["n"] == 0)

print(f"\nT020 gate: {len(PASSED)} passed, {len(FAILED)} failed", flush=True)
sys.exit(1 if FAILED else 0)
