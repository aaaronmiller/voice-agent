"""T012 gate probe: permission denial / revocation / removal handling.

Runs as a script: ``python3 -m echo_node.tests.test_capture_guard``
from ``v2/``. Cross-platform: OS probes are monkeypatched; the real
``CaptureGuard`` state machine + both wiring points are exercised.

Cases (EVAL-011 procedure, logic half):
1. denial — consent probe says Deny → capture refused with OS guidance,
   no retry (second check still refused WITHOUT re-probing).
2. revocation — allowed, then consent flips to Deny → next check refuses.
3. removal — no input devices → refused with device guidance.
4. no retry loops — disabled state sticks across checks (probe count
   does not grow while disabled).
5. disarm sticky — user disarms, permission restores → still refused;
   only explicit re_arm clears.
6. runtime loss — report_runtime_loss stops capture, preserves chunk count.
7. wiring — Recorder.record_turn + dictate_once honor a denying guard
   (return None / failure, never touch the mic).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from echo_node.capture_guard import CaptureGuard

PASSED: list[str] = []
FAILED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    (PASSED if ok else FAILED).append(label)
    print(f"[{'ok' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""),
          flush=True)


def _deny_guard(os_name: str = "nt") -> CaptureGuard:
    g = CaptureGuard(os_name=os_name)
    g.probe_consent = lambda: (False, "ConsentStore\\microphone = Deny")
    g.probe_devices = lambda: (True, "1 input device(s)", ["mic"])
    return g


# 1. denial ----------------------------------------------------------------
g = _deny_guard()
s1 = g.check_capture()
check("denial refuses capture", not s1.allowed, s1.reason)
check("denial names guidance", "ms-settings:privacy-microphone" in s1.guidance,
      s1.guidance[:60])
probes_after_first = g.checks
s2 = g.check_capture()
check("denial sticks (no retry loop)", not s2.allowed and s2.reason == s1.reason)
check("no re-probe while disabled", g.checks == probes_after_first + 1,
      f"checks={g.checks}")

# 2. revocation: allowed then consent flips --------------------------------
g2 = CaptureGuard(os_name="nt")
g2.probe_consent = lambda: (True, "Allow")
g2.probe_devices = lambda: (True, "1 input device(s)", ["mic"])
check("healthy allows capture", g2.check_capture().allowed)
g2.probe_consent = lambda: (False, "ConsentStore\\microphone = Deny")
s = g2.check_capture()
check("revocation disables", not s.allowed and "permission" in s.reason, s.reason)

# 3. removal ----------------------------------------------------------------
g3 = CaptureGuard(os_name="nt")
g3.probe_consent = lambda: (True, "Allow")
g3.probe_devices = lambda: (False, "no input devices enumerated", [])
s = g3.check_capture()
check("removal refuses capture", not s.allowed, s.reason)
check("removal guidance names device",
      "Device Manager" in s.guidance or "Reconnect" in s.guidance,
      s.guidance[:60])

# 3b. linux guidance differs -------------------------------------------------
g3l = CaptureGuard(os_name="posix")
g3l.probe_consent = lambda: (True, "non-Windows")
g3l.probe_devices = lambda: (False, "none", [])
s = g3l.check_capture()
check("linux guidance is platform-appropriate", "pactl" in s.guidance,
      s.guidance[:60])

# 5. disarm sticky ------------------------------------------------------------
g5 = CaptureGuard(os_name="nt")
g5.probe_consent = lambda: (True, "Allow")
g5.probe_devices = lambda: (True, "1", ["mic"])
g5.disarm()
s = g5.check_capture()
check("disarmed refuses even when healthy", not s.allowed and s.reason == "disarmed")
g5.probe_consent = lambda: (True, "Allow")  # permission "restores"
s = g5.check_capture()
check("restore never re-arms disarmed dialogue", not s.allowed, s.reason)
s = g5.re_arm()
check("explicit re_arm restores capture", s.allowed, s.reason)

# 6. runtime loss --------------------------------------------------------------
g6 = CaptureGuard(os_name="nt")
g6.probe_consent = lambda: (True, "Allow")
g6.probe_devices = lambda: (True, "1", ["mic"])
assert g6.check_capture().allowed
s = g6.report_runtime_loss(OSError("device unplugged"), chunks_preserved=42)
check("runtime loss disables", not s.allowed, s.reason)
check("session chunks preserved", s.detail.get("chunks_preserved") == 42)
s = g6.check_capture()
check("post-loss capture stays disabled", not s.allowed)

# 7. wiring: recorder honors guard ----------------------------------------------
from echo_node.components.vad import Recorder

calls = {"read": 0}


class _DeadMic:
    def read(self):
        calls["read"] += 1
        raise AssertionError("mic must not be touched when guard denies")


class _NoVad:
    def is_speech(self, samples):
        return False


rec = Recorder(_DeadMic(), _NoVad(), {})  # type: ignore[arg-type]
out = rec.record_turn(guard=_deny_guard())
check("recorder returns None on denial", out is None)
check("recorder never touches mic", calls["read"] == 0)

# 7b. wiring: dictate_once honors guard ------------------------------------------
import echo_node.dictation as D

D._require_windows = lambda: None
touched = {"rec": False}
out = D.dictate_once(
    record_fn=lambda: (touched.update(rec=True), "/tmp/x.wav")[1],
    transcribe_fn=lambda p: "should never happen",
    guard=_deny_guard())
check("dictate refuses on denial", not out.ok and "capture disabled" in out.reason,
      out.reason)
check("dictate never records", not touched["rec"])

print(f"\nT012 gate: {len(PASSED)} passed, {len(FAILED)} failed", flush=True)
sys.exit(1 if FAILED else 0)
