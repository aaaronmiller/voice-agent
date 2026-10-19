"""Capture permission / device-loss guard (T012, SPEC-011).

Owns the capture-availability state machine. Every capture entry
(``Recorder.record_turn``, ``dictation.record_utterance``) calls
:meth:`CaptureGuard.check_capture` FIRST — on denial/revocation/removal
capture is disabled with actionable OS guidance and NO retry loops.
Runtime loss mid-turn stops capture and preserves session data.
Restoring permission never re-arms a deliberately disarmed dialogue.

States: ``armed`` (capture allowed) → ``disabled:<reason>`` (terminal
until re-checked) → ``armed`` only via explicit user re-arm, never
automatically. ``disarmed`` (user choice) is sticky across permission
changes: even a healthy device never flips ``disarmed`` back.

OS mapping (Windows):
- consent registry ``HKCU:...\\ConsentStore\\microphone`` value
  ``Deny`` = denied at OS level → guidance ``ms-settings:privacy-microphone``.
- WASAPI/MMDevice: no input devices enumerated (sounddevice query) =
  removed → guidance names Device Manager / reconnection.
- ``InputStream`` open/read raising ``PortAudioError`` mid-turn =
  runtime loss → stop, preserve chunks recorded so far.

On non-Windows the same logic runs against ``sounddevice`` (proven on
Linux: RDPSink/RDPSource only) — guidance strings are per-OS.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

GUIDANCE_WINDOWS_MIC = (
    "Microphone blocked. Open Settings → Privacy & security → Microphone "
    "(ms-settings:privacy-microphone), allow access for this app, then re-arm.")
GUIDANCE_WINDOWS_NO_DEVICE = (
    "No microphone found. Reconnect the device, check Device Manager → "
    "Audio inputs and outputs, then re-arm.")
GUIDANCE_LINUX_MIC = (
    "Microphone blocked or missing. Check PipeWire/PulseAudio sources "
    "(pactl list short sources) and permissions, then re-arm.")

DISARMED_NOTE = ("Dialogue was deliberately disarmed — restoring permission "
                 "does not re-arm it. Re-arm explicitly.")


@dataclass
class CaptureStatus:
    allowed: bool
    reason: str = ""
    guidance: str = ""
    detail: dict[str, Any] = field(default_factory=dict)


class CaptureGuard:
    """Sticky permission/device state. One per process (dialogue + dictation share it)."""

    def __init__(self, os_name: str | None = None):
        self._os = os_name or os.name
        self.disarmed_by_user = False
        self.disabled_reason: str | None = None
        self.disabled_at: float | None = None
        self.checks = 0

    # ── user intent ──────────────────────────────────────────────

    def disarm(self) -> None:
        """User deliberately stopped capture. Sticky."""
        self.disarmed_by_user = True

    def re_arm(self) -> CaptureStatus:
        """Explicit user re-arm: clears disarm + disabled, re-probes."""
        self.disarmed_by_user = False
        self.disabled_reason = None
        self.disabled_at = None
        return self.check_capture()

    # ── probing ──────────────────────────────────────────────────

    def probe_consent(self) -> tuple[bool, str]:
        """OS-level mic permission. (allowed, detail). Never raises."""
        try:
            if self._os == "nt":
                return self._probe_windows_consent()
            return True, "non-Windows: consent managed by audio server"
        except Exception as exc:  # noqa: BLE001 — probe must never raise
            return False, f"consent probe failed: {type(exc).__name__}"

    def _probe_windows_consent(self) -> tuple[bool, str]:
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone")
            value, _ = winreg.QueryValueEx(key, "Value")
            winreg.CloseKey(key)
            if str(value).lower() == "deny":
                return False, "ConsentStore\\microphone = Deny"
            return True, f"ConsentStore\\microphone = {value}"
        except FileNotFoundError:
            return True, "no ConsentStore microphone key (default allow)"
        except ImportError:
            return False, "winreg unavailable"

    def probe_devices(self) -> tuple[bool, str, list[str]]:
        """Any input device present? (present, detail, names). Never raises."""
        try:
            import sounddevice as sd
            names = [d["name"] for d in sd.query_devices()
                     if d.get("max_input_channels", 0) > 0]
            if names:
                return True, f"{len(names)} input device(s)", names
            return False, "no input devices enumerated", []
        except Exception as exc:  # noqa: BLE001 — probe must never raise
            return False, f"device probe failed: {type(exc).__name__}", []

    # ── gate ─────────────────────────────────────────────────────

    def check_capture(self) -> CaptureStatus:
        """Decide whether a new capture may start. Call before capture."""
        self.checks += 1
        if self.disarmed_by_user:
            return CaptureStatus(
                allowed=False, reason="disarmed",
                guidance="Dialogue is disarmed. Re-arm explicitly to capture.")
        if self.disabled_reason is not None:
            # No retry loops: stay disabled until explicit re-arm.
            return CaptureStatus(
                allowed=False, reason=self.disabled_reason,
                guidance=self._guidance_for(self.disabled_reason))
        consent_ok, consent_detail = self.probe_consent()
        if not consent_ok:
            return self._disable("permission-denied", consent_detail)
        devices_ok, devices_detail, names = self.probe_devices()
        if not devices_ok:
            return self._disable("no-device", devices_detail)
        return CaptureStatus(allowed=True, reason="ok",
                             detail={"consent": consent_detail,
                                     "devices": names[:5]})

    def report_runtime_loss(self, error: Exception,
                            chunks_preserved: int = 0) -> CaptureStatus:
        """Mid-turn device failure: stop capture, preserve session data."""
        reason = f"runtime-loss ({type(error).__name__})"
        status = self._disable("runtime-loss", str(error) or reason)
        status.detail["chunks_preserved"] = chunks_preserved
        return status

    # ── internals ────────────────────────────────────────────────

    def _disable(self, reason: str, detail: str) -> CaptureStatus:
        self.disabled_reason = reason
        self.disabled_at = time.monotonic()
        return CaptureStatus(allowed=False, reason=reason,
                             guidance=self._guidance_for(reason),
                             detail={"detail": detail})

    def _guidance_for(self, reason: str) -> str:
        if self._os == "nt":
            if reason == "no-device":
                return GUIDANCE_WINDOWS_NO_DEVICE
            return GUIDANCE_WINDOWS_MIC
        return GUIDANCE_LINUX_MIC
