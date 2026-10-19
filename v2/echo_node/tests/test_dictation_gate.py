"""T011 gate probe: dictation insert/restore/precedence/focus logic.

Runs as a script: ``python3 -m echo_node.tests.test_dictation_gate``
from ``v2/``. Cross-platform: Windows-only syscalls are monkeypatched
with fakes; the real ``dictate_once`` control flow is exercised.

Cases (EVAL-006 procedure, logic half):
1. happy path — transcribe "hello world" → pasted once, prior
   clipboard restored.
2. precedence — clipboard changes during transcription → newer copy
   wins, nothing pasted.
3. focus change — foreground window differs at insert → abort, prior
   clipboard restored, nothing pasted anywhere else.
4. transcription failure — clipboard restored, nothing pasted.
5. empty transcription — nothing inserted.
6. conflicting ... not here (T010 owns trigger conflicts).

The hardware half (real mic, real paste into Notepad on SPECTRE-16)
runs on Windows and appends its evidence to the ledger — this probe
does not claim it.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import echo_node.dictation as D

PASSED: list[str] = []
FAILED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    (PASSED if ok else FAILED).append(label)
    print(f"[{'ok' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""),
          flush=True)


class FakeWindows:
    """Fake clipboard + focus + paste sink."""

    def __init__(self, clipboard: str = "prior"):
        self.clipboard = clipboard
        self.focus = 1001
        self.pastes: list[tuple[int, str]] = []  # (focus_hwnd, text)
        self._mutate_midflight = None

    def install(self) -> None:
        # Stub the gate, NOT os.name (pathlib.Path dispatches on it).
        D._require_windows = lambda: None
        D.get_foreground_window = lambda: self.focus
        D.read_clipboard_text = lambda: (True, self.clipboard)
        def _write(text: str) -> bool:
            self.clipboard = text
            # concurrent-copy hook: mutate mid-flight when armed
            if self._mutate_midflight is not None:
                fn, self._mutate_midflight = self._mutate_midflight, None
                fn()
            return True
        D.write_clipboard_text = _write
        def _paste() -> None:
            self.pastes.append((self.focus, self.clipboard))
        D.send_paste = _paste


def run_case(fake: FakeWindows, record_text: str = "hello world",
             transcribe=None, record=None) -> D.DictationResult:
    import tempfile
    fd, tmp = tempfile.mkstemp(prefix="fake-dict-", suffix=".wav")
    os.close(fd)
    rec = record or (lambda: tmp)
    tra = transcribe or (lambda p: record_text)
    try:
        return D.dictate_once(record_fn=rec, transcribe_fn=tra)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# 1. happy path ------------------------------------------------------------
fake = FakeWindows(clipboard="prior-content")
fake.install()
res = run_case(fake)
check("happy path ok", res.ok and res.pasted, res.reason)
check("inserted exactly once", len(fake.pastes) == 1,
      f"pastes={fake.pastes}")
check("pasted into trigger focus", fake.pastes and fake.pastes[0][0] == 1001)
check("prior clipboard restored",
      fake.clipboard == "prior-content", repr(fake.clipboard))

# 2. precedence: concurrent copy during transcription -----------------------
fake = FakeWindows(clipboard="prior-content")
fake.install()
def _transcribe_with_copy(path):
    fake.clipboard = "newer-concurrent-copy"  # user copied mid-transcription
    return "stale transcription"
res = run_case(fake, transcribe=_transcribe_with_copy)
check("concurrent copy wins (not ok)", not res.ok, res.reason)
check("nothing pasted on precedence", len(fake.pastes) == 0)
check("newer copy preserved", fake.clipboard == "newer-concurrent-copy",
      repr(fake.clipboard))

# 3. focus change aborts ----------------------------------------------------
fake = FakeWindows(clipboard="prior-content")
fake.install()
def _transcribe_with_focus_change(path):
    fake.focus = 9999  # user alt-tabbed mid-transcription
    return "hello world"
res = run_case(fake, transcribe=_transcribe_with_focus_change)
check("focus change aborts", not res.ok, res.reason)
check("nothing pasted on focus change", len(fake.pastes) == 0,
      f"pastes={fake.pastes}")
check("clipboard restored on focus abort", fake.clipboard == "prior-content",
      repr(fake.clipboard))

# 4. transcription failure ---------------------------------------------------
fake = FakeWindows(clipboard="prior-content")
fake.install()
def _boom(path):
    raise RuntimeError("model blew up")
res = run_case(fake, transcribe=_boom)
check("transcription failure reported", not res.ok and "transcription failed" in res.reason,
      res.reason)
check("nothing pasted on failure", len(fake.pastes) == 0)
check("clipboard intact on failure", fake.clipboard == "prior-content")

# 4b. capture failure ---------------------------------------------------------
fake = FakeWindows(clipboard="prior-content")
fake.install()
def _rec_boom():
    raise RuntimeError("no mic")
res = run_case(fake, record=_rec_boom)
check("capture failure reported", not res.ok and "capture failed" in res.reason,
      res.reason)
check("nothing pasted on capture failure", len(fake.pastes) == 0)

# 5. empty transcription -------------------------------------------------------
fake = FakeWindows(clipboard="prior-content")
fake.install()
res = run_case(fake, record_text="   ")
check("empty transcription inserts nothing", not res.ok, res.reason)
check("nothing pasted on empty", len(fake.pastes) == 0)

print(f"\nT011-logic gate: {len(PASSED)} passed, {len(FAILED)} failed", flush=True)
sys.exit(1 if FAILED else 0)
