"""Central provider registry for Echo-Node v2 (Phase A).

Registration is explicit in-code via :func:`register_builtin` — every
built-in provider is imported and registered by name. The design leaves
room for packaging entry-points later (``echo_node.stt`` etc.) without
changing the registry API.

``registry.working(slot)`` is the only source settings dropdowns may
use: providers that fail validation are excluded (unless
``include_experimental`` / ``ECHO_INCLUDE_EXPERIMENTAL`` opts in to
experimental ones that passed).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable

from echo_node.slots import Capability, SlotType
from echo_node.slots.validation import ValidationResult


# ── Provider info ───────────────────────────────────────────────────

@dataclass
class ProviderInfo:
    name: str                        # config key, e.g. "kokoro"
    slot: SlotType
    provider_cls: type
    capabilities: Capability
    experimental: bool = False
    last_validation: ValidationResult | None = None
    # True for providers declared in config.yaml's `external_providers:`
    # (Phase B subprocess adapters). The settings UI marks these so users
    # can tell them apart from built-ins.
    external: bool = False
    # Optional override for cls.validate (used when one class is
    # registered under several names with different probes, e.g. alsa
    # vs sounddevice sharing MicStream).
    validate_fn: Callable[[dict[str, Any] | None], ValidationResult] | None = None

    def validate(self, config: dict[str, Any] | None = None) -> ValidationResult:
        try:
            if self.validate_fn is not None:
                result = self.validate_fn(config)
            else:
                result = self.provider_cls.validate(config)
            if not isinstance(result, ValidationResult):
                result = ValidationResult(False, f"validator returned {type(result).__name__}, not ValidationResult", {})
        except Exception as exc:
            # Validators must never crash the registry — record the failure.
            result = ValidationResult(False, f"validator raised {type(exc).__name__}: {exc}", {})
        self.last_validation = result
        return result


# ── Registry ────────────────────────────────────────────────────────

def _env_includes_experimental() -> bool:
    return os.environ.get("ECHO_INCLUDE_EXPERIMENTAL", "").lower() in {"1", "true", "yes"}


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[tuple[SlotType, str], ProviderInfo] = {}

    def register(
        self,
        slot: SlotType,
        name: str,
        provider_cls: type,
        *,
        experimental: bool = False,
        external: bool = False,
        capabilities: Capability | None = None,
        validate_fn: Callable[[dict[str, Any] | None], ValidationResult] | None = None,
    ) -> ProviderInfo:
        info = ProviderInfo(
            name=name,
            slot=slot,
            provider_cls=provider_cls,
            capabilities=capabilities or provider_cls.capabilities(),
            experimental=experimental,
            external=external,
            validate_fn=validate_fn,
        )
        self._providers[(slot, name)] = info
        return info

    def get(self, slot: SlotType, name: str) -> type:
        """Return the provider class for (slot, name).

        Raises KeyError for an unknown name — callers keep their
        historical fallback behavior (see create_stt/create_tts).
        """
        try:
            return self._providers[(slot, name)].provider_cls
        except KeyError:
            known = ", ".join(sorted(self.all_names(slot)))
            raise KeyError(f"Unknown {slot.value} provider {name!r} (known: {known})")

    def info(self, slot: SlotType, name: str) -> ProviderInfo:
        return self._providers[(slot, name)]

    def unregister(self, slot: SlotType, name: str) -> bool:
        """Remove ``(slot, name)`` from the registry.

        Used by the external-provider settings flow to replace a live
        registration (unregister-then-register on save, unregister on
        remove). Returns True when an entry was actually removed; never
        raises. Built-ins are never unregistered by that flow — it only
        ever passes names that came from ``external_providers:``.
        """
        return self._providers.pop((slot, name), None) is not None

    def all_names(self, slot: SlotType) -> list[str]:
        return sorted(n for (s, n) in self._providers if s is slot)

    def all_providers(self, slot: SlotType) -> list[ProviderInfo]:
        return [self._providers[(slot, n)] for n in self.all_names(slot)]

    def working(
        self,
        slot: SlotType,
        *,
        include_experimental: bool | None = None,
        config: dict[str, Any] | None = None,
    ) -> list[ProviderInfo]:
        """Providers that pass validation — the only valid dropdown source.

        Results are cached on each ProviderInfo (see refresh() to re-run).
        """
        if include_experimental is None:
            include_experimental = _env_includes_experimental()
        out: list[ProviderInfo] = []
        for info in self.all_providers(slot):
            if info.experimental and not include_experimental:
                continue
            result = info.last_validation or info.validate(config)
            if result.ok:
                out.append(info)
        return out

    def refresh(
        self,
        slot: SlotType | None = None,
        name: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Re-run validators (clearing the cache) for one or all providers."""
        for (s, n), info in self._providers.items():
            if slot is not None and s is not slot:
                continue
            if name is not None and n != name:
                continue
            info.last_validation = None
            info.validate(config)

    def validate_all(self) -> dict[str, dict[str, Any]]:
        """Run every provider's validator; return a JSON-able report."""
        report: dict[str, dict[str, Any]] = {}
        for (slot, name) in sorted(self._providers, key=lambda k: (k[0].value, k[1])):
            info = self._providers[(slot, name)]
            result = info.validate()
            report[f"{slot.value}/{name}"] = {
                "ok": result.ok,
                "reason": result.reason,
                "details": result.details,
                "experimental": info.experimental,
                "class": f"{info.provider_cls.__module__}.{info.provider_cls.__name__}",
            }
        return report


# ── Built-in registration ───────────────────────────────────────────

def register_builtin(reg: ProviderRegistry | None = None) -> ProviderRegistry:
    """Import and register every first-party provider under the exact
    config names already in use (config.example.yaml, assistant_v2.py,
    incarnations.yaml). No behavior change — purely additive."""
    from echo_node.slots import validation as _v

    reg = reg if reg is not None else ProviderRegistry()

    # ── STT ──
    from echo_node.components.stt import FasterWhisperSTT, ParakeetSTT
    reg.register(SlotType.STT, "faster-whisper", FasterWhisperSTT)
    reg.register(SlotType.STT, "parakeet", ParakeetSTT)
    # "onnx-asr" is the config.example.yaml name for the same Parakeet backend
    reg.register(SlotType.STT, "onnx-asr", ParakeetSTT,
                 capabilities=ParakeetSTT.capabilities())

    # ── TTS ──
    from echo_node.components.tts import (
        KokoroTTS, DotsTTS, CosyVoice3TTS, EspeakTTS, Qwen3TTS, VoxCPMTTS,
    )
    reg.register(SlotType.TTS, "kokoro", KokoroTTS)
    reg.register(SlotType.TTS, "dots", DotsTTS)
    reg.register(SlotType.TTS, "cosyvoice3", CosyVoice3TTS, experimental=True)
    # Phase C: streaming + expressive tiers; experimental until validated
    # on target hardware. Defaults unchanged (kokoro stays default).
    reg.register(SlotType.TTS, "qwen3-tts", Qwen3TTS, experimental=True)
    reg.register(SlotType.TTS, "voxcpn", VoxCPMTTS, experimental=True)
    reg.register(SlotType.TTS, "espeak-ng", EspeakTTS)

    # ── VAD / wake word ──
    from echo_node.components.vad import OpenWakeWordVad, SileroVAD
    from echo_node.components.wake import WakeDetector
    reg.register(SlotType.VAD, "openwakeword", OpenWakeWordVad)
    # Phase C: real Silero v6; experimental until validated on hardware.
    # Default stays openwakeword.
    reg.register(SlotType.VAD, "silero", SileroVAD, experimental=True)
    reg.register(SlotType.WAKE_WORD, "openwakeword", WakeDetector)

    # ── Audio I/O (alsa vs sounddevice share MicStream; probes differ) ──
    from echo_node.components.audio import MicStream

    def _validate_alsa(cfg: dict[str, Any] | None) -> ValidationResult:
        arecord_ok, arecord_info = _v.check_binary("arecord")
        aplay_ok, aplay_info = _v.check_binary("aplay")
        if arecord_ok and aplay_ok:
            return _v.ok_result("arecord+aplay present",
                                {"arecord": arecord_info, "aplay": aplay_info})
        return _v.missing_result("arecord/aplay",
                                 {"arecord": arecord_info, "aplay": aplay_info})

    def _validate_sounddevice(cfg: dict[str, Any] | None) -> ValidationResult:
        found, ver = _v.check_module("sounddevice")
        if found:
            return _v.ok_result(f"sounddevice {ver}", {})
        return _v.missing_result("sounddevice", {"module": "sounddevice"})

    reg.register(
        SlotType.AUDIO_IO, "alsa", MicStream,
        capabilities=Capability(
            name="alsa", version="unknown", languages=[],
            streaming=True, license="GPL-2.0", network=False,
            notes="mic via arecord, playback via aplay",
        ),
        validate_fn=_validate_alsa,
    )
    reg.register(
        SlotType.AUDIO_IO, "sounddevice", MicStream,
        capabilities=Capability(
            name="sounddevice", version="unknown", languages=[],
            streaming=True, license="MIT", network=False,
            notes="mic/playback via the sounddevice (PortAudio) Python module",
        ),
        validate_fn=_validate_sounddevice,
    )

    # ── Barge-in policy ──
    from echo_node.components.barge_in import VadGatedBargeIn
    reg.register(SlotType.BARGE_IN, "vad_gated", VadGatedBargeIn)

    # ── AEC (Phase C): WebRTC AEC3 wrapper around mic capture ──
    from echo_node.components.aec import AecAudioIO
    reg.register(SlotType.AUDIO_IO, "aec-webrtc", AecAudioIO, experimental=True)

    # ── Agent backends (ABC + REGISTRY already live in echo_node.backends) ──
    from echo_node import backends as _b
    for _key, _cls in _b.REGISTRY.items():
        reg.register(
            SlotType.AGENT_BACKEND, _key, _cls,
            experimental=_key in _b.EXPERIMENTAL_BACKENDS,
        )

    # ── Avatar renderers ──
    try:
        from avatar.controller import AvatarController
        reg.register(SlotType.AVATAR, "rhubarb", AvatarController)
    except ImportError as exc:
        # avatar/ is a UI-layer package; the core pipeline must not
        # depend on it being importable.
        reg.register(
            SlotType.AVATAR, "rhubarb", type("MissingAvatarController", (), {}),
            capabilities=Capability(
                name="rhubarb", license="unknown", network=False,
                notes=f"avatar.controller not importable here: {exc}",
            ),
            validate_fn=lambda cfg, _exc=exc: _v.missing_result(
                "avatar.controller", {"import_error": str(_exc)}),
        )
    # Phase C: LiveTalking-style harness around the MuseTalk prototype —
    # genuinely implements the AvatarRenderer contract (preload/play/stop),
    # experimental until validated on target hardware.
    try:
        from avatar_video.livetalking_musetalk import LiveTalkingMuseTalk
        reg.register(SlotType.AVATAR, "musetalk-livetalking", LiveTalkingMuseTalk,
                     experimental=True)
    except ImportError as exc:
        reg.register(
            SlotType.AVATAR, "musetalk-livetalking", type("MissingLiveTalkingMuseTalk", (), {}),
            experimental=True,
            capabilities=Capability(
                name="musetalk-livetalking", gpu_required=True, license="unknown",
                network=False,
                notes=(f"avatar_video.livetalking_musetalk not importable here: {exc}"),
            ),
            validate_fn=lambda cfg, _exc=exc: _v.missing_result(
                "avatar_video.livetalking_musetalk", {"import_error": str(_exc)}),
        )
    try:
        from avatar_video.musetalk_assistant import MuseTalkRenderer
        reg.register(SlotType.AVATAR, "musetalk", MuseTalkRenderer, experimental=True)
    except ImportError as exc:
        reg.register(
            SlotType.AVATAR, "musetalk", type("MissingMuseTalkRenderer", (), {}),
            experimental=True,
            capabilities=Capability(
                name="musetalk", gpu_required=True, license="unknown",
                network=False,
                notes=(f"avatar_video.musetalk_assistant not importable here: {exc}; "
                       "prototype does not implement the AvatarRenderer contract"),
            ),
            validate_fn=lambda cfg, _exc=exc: _v.missing_result(
                "avatar_video.musetalk_assistant", {"import_error": str(_exc)}),
        )

    return reg


# ── Singleton ───────────────────────────────────────────────────────

_registry: ProviderRegistry | None = None


def get_registry() -> ProviderRegistry:
    """Process-wide registry; built-ins are registered on first use."""
    global _registry
    if _registry is None:
        _registry = register_builtin()
    return _registry


class _RegistryProxy:
    """Lets ``from echo_node.slots.registry import registry`` work while
    keeping built-in registration lazy."""

    def __getattr__(self, name: str) -> Any:
        return getattr(get_registry(), name)


registry = _RegistryProxy()


__all__ = [
    "ProviderInfo",
    "ProviderRegistry",
    "register_builtin",
    "get_registry",
    "registry",
]
