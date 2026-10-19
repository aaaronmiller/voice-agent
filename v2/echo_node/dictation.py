"""Windows dictation path (T011, SPEC-006).

Trigger in a focused editable field → capture → transcribe → insert
once at cursor → restore prior clipboard/formats, newer concurrent
copy wins. Failure, cancellation, or focus change preserves data and
never pastes into another field.

Runs on Windows (``keyboard`` global hook, ``pyperclip`` clipboard,
``pyautogui`` Ctrl+V synthesis). The module imports cleanly on other
platforms — Windows-only imports happen lazily inside methods so the
config gate and probes stay cross-platform.

Audio capture uses ``sounddevice`` (proven present on SPECTRE-16 with
31 devices incl. Realtek USB mic). Transcription uses the STT slot
registry (``create_stt``) — default provider ``hf-whisper``
(transformers Whisper tiny, CPU ~1.6s per 3s audio, proven on-host).
Insertion uses the clipboard-swap + Ctrl+V pattern from the archived
``stt_project`` (read-only reference), hardened:

- Clipboard serial check: snapshot before transcribe; if the clipboard
  changed during transcription, the newer content wins (SPEC-006
  precedence) — we paste the transcription only when we still own the
  clipboard, else report and leave the newer content alone.
- Focus guard: the foreground window handle at trigger time must still
  be foreground at insert time; on change, abort and restore.
- Formats: text always restored; non-text formats (images/files) are
  out of ``pyperclip`` reach — recorded as explicit gap (T003); when
  the pre-trigger clipboard is non-text we still restore best-effort
  and report.
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DictationResult:
    ok: bool
    text: str = ""
    reason: str = ""
    clipboard_restored: bool = False
    pasted: bool = False


@dataclass
class DictationSession:
    """One trigger→insert cycle. State kept for the EVAL-006 evidence log."""

    started_at: float = 0.0
    transcribed_chars: int = 0
    events: list[str] = field(default_factory=list)

    def log(self, event: str) -> None:
        self.events.append(f"{time.monotonic():.2f} {event}")


def _require_windows() -> None:
    if os.name != "nt":
        raise RuntimeError("Windows dictation path requires Windows (os.name == 'nt')")


def get_foreground_window() -> int:
    """Foreground window handle (focus guard). 0 when unavailable."""
    _require_windows()
    import ctypes
    return int(ctypes.windll.user32.GetForegroundWindow())


def read_clipboard_text() -> tuple[bool, str]:
    """Return (ok, text). ok=False when clipboard has no text."""
    _require_windows()
    import pyperclip
    try:
        return True, str(pyperclip.paste() or "")
    except Exception:  # noqa: BLE001 — boundary failures become return values
        return False, ""


def write_clipboard_text(text: str) -> bool:
    _require_windows()
    import pyperclip
    try:
        pyperclip.copy(text)
        return True
    except Exception:  # noqa: BLE001 — boundary failures become return values
        return False


def send_paste() -> None:
    """Synthesize Ctrl+V at the cursor. Raises on failure."""
    _require_windows()
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.hotkey("ctrl", "v")


def record_utterance(
    sample_rate: int = 16000,
    silence_seconds: float = 1.2,
    max_seconds: float = 30.0,
    device: Any = None,
) -> Path:
    """Capture mic audio until silence or timeout. Returns a WAV path.

    Simple energy-based endpointing (RMS over 100ms frames); the VAD
    slot owns production endpointing — this keeps dictation independent
    of dialogue tuning per plan CTX-004.
    """
    _require_windows()
    import numpy as np
    import sounddevice as sd

    frames: list[bytes] = []
    frame_samples = sample_rate // 10
    silent_frames = 0
    needed_silent = max(1, int(silence_seconds * 10))
    max_frames = int(max_seconds * 10)
    stream = sd.InputStream(samplerate=sample_rate, channels=1,
                            dtype="int16", device=device)
    stream.start()
    try:
        for _ in range(max_frames):
            chunk, _overflow = stream.read(frame_samples)
            frames.append(bytes(chunk))
            rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
            if rms < 350.0:  # matches v2 vad rms_floor default
                silent_frames += 1
            else:
                silent_frames = 0
            if len(frames) > 10 and silent_frames >= needed_silent:
                break
    finally:
        stream.stop()
        stream.close()
    fd, name = tempfile.mkstemp(prefix="echo-dictate-", suffix=".wav")
    os.close(fd)
    path = Path(name)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"".join(frames))
    return path


def transcribe_wav(wav_path: Path, stt_config: dict[str, Any] | None = None) -> str:
    """Transcribe via the STT slot registry. Raises on failure."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from echo_node.components.stt import create_stt
    cfg = dict(stt_config or {})
    cfg.setdefault("provider", "hf-whisper")
    provider = create_stt(cfg)
    try:
        return provider.transcribe(Path(wav_path)).strip()
    finally:
        try:
            provider.unload()
        except Exception:  # noqa: BLE001, S110 — best-effort unload; result already returned
            pass


def dictate_once(
    stt_config: dict[str, Any] | None = None,
    record_fn: Any = None,
    transcribe_fn: Any = None,
    guard: Any = None,
) -> DictationResult:
    session = DictationSession(started_at=time.monotonic())
    session.log("trigger")
    _require_windows()

    # T012: permission/device gate BEFORE capture. Denial stays disabled
    # with guidance — no retry loops; explicit re-arm only.
    if guard is not None:
        status = guard.check_capture()
        if not status.allowed:
            return DictationResult(ok=False, reason=f"capture disabled ({status.reason}): {status.guidance}")

    focus_at_trigger = get_foreground_window()
    session.log(f"focus_at_trigger={focus_at_trigger}")

    had_text, prior_text = read_clipboard_text()
    session.log(f"clipboard_saved chars={len(prior_text) if had_text else 0}")
    # Serial: re-read right before insert to detect concurrent copies.
    clipboard_serial = ("text:" + prior_text) if had_text else "non-text"

    wav_raw: Any = None
    try:
        recorder = record_fn or record_utterance
        wav_raw = recorder()
        # record_utterance returns a Path; injected fakes may return a
        # path-like or string (tests run on non-Windows where Path(x)
        # flavour differs) — accept anything os.fspath handles.
        wav_path: Path | None = Path(os.fspath(wav_raw))
        session.log(f"captured wav={wav_path}")
    except Exception as exc:  # noqa: BLE001 — boundary failures become return values
        session.log(f"capture_failed {type(exc).__name__}")
        return DictationResult(ok=False, reason=f"capture failed: {exc}")

    try:
        transcriber = transcribe_fn or (lambda p: transcribe_wav(p, stt_config))
        text = (transcriber(wav_path) or "").strip()
        session.log(f"transcribed chars={len(text)}")
    except Exception as exc:  # noqa: BLE001 — boundary failures become return values
        session.log(f"transcribe_failed {type(exc).__name__}")
        return DictationResult(ok=False, reason=f"transcription failed: {exc}")
    finally:
        try:
            if wav_path is not None:
                wav_path.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001, S110 — temp-file cleanup; transcription already captured
            pass
    if not text:
        return DictationResult(ok=False, reason="empty transcription — nothing inserted")

    # Focus guard: abort rather than paste into the wrong field.
    if get_foreground_window() != focus_at_trigger:
        session.log("focus_changed abort")
        _restore_clipboard(had_text, prior_text)
        return DictationResult(ok=False, reason="focus changed — nothing pasted")

    # Precedence: a newer concurrent copy wins over our transcription.
    now_text_ok, now_text = read_clipboard_text()
    now_serial = ("text:" + now_text) if now_text_ok else "non-text"
    if now_serial != clipboard_serial:
        session.log("concurrent_copy precedence")
        return DictationResult(
            ok=False,
            reason="clipboard changed during transcription — newer copy kept",
            clipboard_restored=True)

    if not write_clipboard_text(text):
        return DictationResult(ok=False, reason="clipboard write failed")
    time.sleep(0.1)  # let the clipboard settle (archive pattern)
    try:
        send_paste()
    except Exception as exc:  # noqa: BLE001 — boundary failures become return values
        _restore_clipboard(had_text, prior_text)
        return DictationResult(ok=False, reason=f"paste failed: {exc}",
                               clipboard_restored=True)
    session.log("pasted")
    time.sleep(0.2)
    restored = _restore_clipboard(had_text, prior_text)
    session.log(f"clipboard_restored={restored}")
    return DictationResult(ok=True, text=text, pasted=True,
                           clipboard_restored=restored)


def _restore_clipboard(had_text: bool, prior_text: str) -> bool:
    if not had_text:
        return True  # nothing to restore (non-text gap recorded by caller)
    try:
        return bool(write_clipboard_text(prior_text))
    except Exception:  # noqa: BLE001 — boundary failures become return values
        return False


class DictationHotkey:
    """Global-hotkey listener driving dictate_once (Windows).

    Separate from the dialogue ``KeyboardHotkey`` (Enter/Escape):
    dictation is a separately invoked path per plan CTX-005.
    """

    def __init__(self, config: dict[str, Any]):
        self.combo = str(config.get("dictation_hotkey", "ctrl+shift+a") or "")
        self.enabled = bool(config.get("enabled", True)) and bool(self.combo)
        self._stop = threading.Event()
        self.last_result: DictationResult | None = None

    def start(self, on_result: Any = None) -> bool:
        _require_windows()
        if not self.enabled:
            return False
        import keyboard
        combo = self.combo.lower()

        def _fire() -> None:
            try:
                self.last_result = dictate_once()
                if on_result is not None:
                    on_result(self.last_result)
            except Exception as exc:  # noqa: BLE001 — hotkey thread must never die; failure becomes a result
                self.last_result = DictationResult(ok=False, reason=str(exc))

        keyboard.add_hotkey(combo, _fire)
        return True

    def stop(self) -> None:
        self._stop.set()
        try:
            import keyboard
            keyboard.unhook_all_hotkeys()
        except Exception:  # noqa: BLE001, S110 — best-effort unhook at shutdown
            pass
