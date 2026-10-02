"""TTS backends: Kokoro (ONNX), dots.tts (GPU), CosyVoice 3 (GPU, experimental), espeak-ng (fallback)."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from echo_node.slots import Capability, TTSProvider
from echo_node.slots.validation import (
    ValidationResult,
    check_binary,
    check_cuda,
    check_module,
    check_paths,
    missing_result,
    ok_result,
)

# v2/ directory (models/, gotit.wav, etc. live here). This module sits at
# v2/echo_node/components/tts.py, so the project root is three levels up.
_V2_ROOT = Path(__file__).resolve().parent.parent.parent


# ── TTS backends ────────────────────────────────────────────────────

class KokoroTTS(TTSProvider):
    def __init__(self, config: dict[str, Any]):
        self.model_path = (_V2_ROOT / str(config.get("model_path", "models/kokoro/kokoro-v1.0.onnx"))).resolve()
        self.voices_path = (_V2_ROOT / str(config.get("voices_path", "models/kokoro/voices-v1.0.bin"))).resolve()
        self.voice = str(config.get("voice", "af_heart"))
        self.speed = float(config.get("speed", 1.0))
        self._kokoro = None

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(
            name="kokoro",
            version="v1.0",
            languages=["en"],
            streaming=False,  # batch: whole sentence per synthesize_to_wav()
            vram_gb=None,
            gpu_required=False,  # ONNX CPU
            license="Apache-2.0",
            network=False,
            notes="default TTS: low-latency ONNX, 82M params",
        )

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        found, ver = check_module("kokoro_onnx")
        if not found:
            return missing_result("kokoro_onnx", {"module": "kokoro_onnx"})
        cfg = config or {}
        model = str(_V2_ROOT / str(cfg.get("model_path", "models/kokoro/kokoro-v1.0.onnx")))
        voices = str(_V2_ROOT / str(cfg.get("voices_path", "models/kokoro/voices-v1.0.bin")))
        missing = check_paths(model, voices)
        if missing:
            return missing_result(f"kokoro model files: {missing[0]}",
                                  {"missing": missing, "module_version": ver})
        return ok_result(f"kokoro_onnx {ver} + model files present",
                         {"version": ver, "model_path": model})

    def load(self) -> None:
        if self._kokoro is not None:
            return
        if not self.model_path.exists() or not self.voices_path.exists():
            raise FileNotFoundError("Kokoro model files missing. Run ./setup.sh.")
        from kokoro_onnx import Kokoro
        started = time.perf_counter()
        self._kokoro = Kokoro(str(self.model_path), str(self.voices_path))
        print(f"[timing] tts_load={time.perf_counter() - started:.2f}s", flush=True)

    def unload(self) -> None:
        if self._kokoro is None:
            return
        del self._kokoro
        self._kokoro = None
        import gc; gc.collect()

    def warm(self) -> None:
        fd, name = tempfile.mkstemp(prefix="echo-node-tts-warm-", suffix=".wav")
        os.close(fd)
        path = Path(name)
        try:
            self.synthesize_to_wav("Ready.", path)
        finally:
            path.unlink(missing_ok=True)

    def synthesize_to_wav(self, text: str, path: Path) -> Path:
        import soundfile as sf
        self.load()
        assert self._kokoro is not None
        audio, sample_rate = self._kokoro.create(text, voice=self.voice, speed=self.speed, lang="en-us")
        sf.write(str(path), audio, sample_rate)
        return path


class DotsTTS(TTSProvider):
    """GPU-accelerated TTS via dots.tts (2B AR model, MeanFlow distillation)."""
    def __init__(self, config: dict[str, Any]):
        from tts_dots import DotsTTS as _DotsTTS
        self._impl = _DotsTTS(config)

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(
            name="dots",
            version="unknown",
            languages=["en", "zh"],
            streaming=True,   # exposes generate_stream()
            vram_gb=4.0,      # 2B AR model; verify on target hardware
            gpu_required=True,
            license="unknown",
            network=False,
            notes="expressive tier; VRAM figure is an estimate — verify on 6GB GPUs",
        )

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        found, ver = check_module("tts_dots")
        if not found:
            return missing_result("tts_dots",
                                   {"module": "tts_dots (v2/tts_dots.py, needs v2 on sys.path)"})
        cuda_ok, cuda_info = check_cuda()
        details = {"module_version": ver, "cuda": cuda_info}
        if not cuda_ok:
            return ValidationResult(False, f"dots.tts needs CUDA: {cuda_info}", details)
        return ok_result(f"tts_dots {ver} + CUDA ({cuda_info})", details)

    def load(self) -> None:
        self._impl.load()

    def unload(self) -> None:
        self._impl.unload()

    def warm(self) -> None:
        self._impl.warm()

    def synthesize_to_wav(self, text: str, path: Path) -> Path:
        started = time.perf_counter()
        result = self._impl.synthesize_to_wav(text, path)
        print(f"[timing] tts_gen={time.perf_counter() - started:.2f}s provider=dots", flush=True)
        return result

    def generate_stream(self, text: str):
        return self._impl.generate_stream(text)

    @property
    def sample_rate(self) -> int:
        return self._impl.sample_rate


class CosyVoice3TTS(TTSProvider):
    """Higher-quality TTS via CosyVoice 3 (0.5B, GPU). Experimental — unverified on this hardware."""
    def __init__(self, config: dict[str, Any]):
        from tts_cosyvoice import CosyVoice3TTS as _CosyVoice3TTS
        self._impl = _CosyVoice3TTS(config)

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(
            name="cosyvoice3",
            version="0.5B",
            languages=["en", "zh"],  # 9 languages+dialects per module docstring
            streaming=True,          # exposes generate_stream(); ~150ms TTFB
            vram_gb=2.0,             # ~1-2GB fp16 per module docstring
            gpu_required=True,       # "CPU works but is far too slow" — treat CUDA as required
            license="Apache-2.0",
            network=False,
            notes="experimental; zero-shot voice cloning from a short reference clip",
        )

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        found, ver = check_module("tts_cosyvoice")
        if not found:
            return missing_result("tts_cosyvoice",
                                   {"module": "tts_cosyvoice (v2/tts_cosyvoice.py, needs v2 on sys.path)"})
        cuda_ok, cuda_info = check_cuda()
        cfg = config or {}
        model_dir = str(_V2_ROOT / str(cfg.get("model_path", "models/cosyvoice3-0.5b")))
        missing = check_paths(model_dir)
        details = {"module_version": ver, "cuda": cuda_info, "model_dir": model_dir}
        problems = []
        if not cuda_ok:
            problems.append(f"CUDA: {cuda_info}")
        if missing:
            problems.append(f"model dir missing: {model_dir}")
        if problems:
            return ValidationResult(False, "; ".join(problems), details)
        return ok_result(f"tts_cosyvoice {ver} + CUDA + model dir present", details)

    def load(self) -> None:
        self._impl.load()

    def unload(self) -> None:
        self._impl.unload()

    def warm(self) -> None:
        self._impl.warm()

    def synthesize_to_wav(self, text: str, path: Path) -> Path:
        started = time.perf_counter()
        result = self._impl.synthesize_to_wav(text, path)
        print(f"[timing] tts_gen={time.perf_counter() - started:.2f}s provider=cosyvoice3", flush=True)
        return result

    def generate_stream(self, text: str):
        return self._impl.generate_stream(text)

    @property
    def sample_rate(self) -> int:
        return self._impl.sample_rate


class Qwen3TTS(TTSProvider):
    """Streaming TTS via Qwen3-TTS-0.6B (Alibaba, Apache-2.0).

    API surface written against the documented upstream package (verified
    2026-10-01 against Qwen/Qwen3-TTS and community mirrors):

        from qwen_tts import Qwen3TTSModel        # pip package ``qwen_tts``
        model = Qwen3TTSModel.from_pretrained(
            "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice", device_map="cuda:0",
            dtype=torch.bfloat16)
        wavs, sr = model.generate_custom_voice(
            text=..., language="English", speaker="Ryan", instruct="")
        # Base (voice-clone) variant:
        wavs, sr = model.generate_voice_clone(
            text=..., language="English", ref_audio="ref.wav", ref_text="...")

    Exact kwarg names of ``generate_custom_voice`` and the transformers-
    native ``Qwen3TTSForConditionalGeneration`` path were NOT exercised on
    this VM (no torch/GPU) — the synthesis call below carries a comment
    where the surface is unverified. ``model_id`` accepts a HF id or a
    local directory (no download inside the validator, ever).
    """
    def __init__(self, config: dict[str, Any]):
        # Presence check only (matches the DotsTTS/CosyVoice3TTS pattern):
        # the model itself loads lazily in load().
        from qwen_tts import Qwen3TTSModel as _Qwen3TTSModel
        self._model_cls = _Qwen3TTSModel
        self.model_id = str(config.get("model_id",
                                       "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"))
        self.speaker = str(config.get("voice", "Ryan"))
        self.language = str(config.get("language", "English"))
        self.instruct = str(config.get("instruct", ""))
        self.device_map = str(config.get("device_map", "cuda:0"))
        self.dtype = str(config.get("dtype", "bfloat16"))
        self._model = None
        self._sample_rate = 24000  # Qwen3-TTS output rate per upstream docs

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(
            name="qwen3-tts",
            version="0.6B (12Hz)",
            languages=["en", "zh", "ja", "ko", "de", "fr", "ru", "es", "pt", "it"],
            streaming=True,   # ~97ms first-packet per ROADMAP survey
            vram_gb=4.0,      # estimate — verify the quantized path fits 6GB VRAM
            gpu_required=True,
            license="Apache-2.0",
            network=False,
            notes=("streaming tier + 3s zero-shot clone (Base variant); "
                   "VRAM/language figures from upstream docs, unverified on "
                   "target hardware; experimental"),
        )

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        found, ver = check_module("qwen_tts")
        if not found:
            return missing_result("qwen_tts",
                                   {"module": "qwen_tts (pip install qwen-tts)"})
        cuda_ok, cuda_info = check_cuda()
        cfg = config or {}
        model_id = str(cfg.get("model_id", "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"))
        details: dict[str, Any] = {"module_version": ver, "cuda": cuda_info,
                                   "model_id": model_id}
        problems = []
        if not cuda_ok:
            problems.append(f"CUDA: {cuda_info}")
        # Local model dir → check presence; HF id → download needed (never here).
        if "/" not in model_id.replace("\\", "/") or Path(model_id).exists() or model_id.startswith((".", "/")):
            missing = check_paths(model_id)
            details["local_model_dir"] = model_id
            if missing:
                problems.append(f"local model dir missing: {model_id}")
        else:
            details["note"] = "HF model id — from_pretrained() would download; never in validate()"
        if problems:
            return ValidationResult(False, "; ".join(problems), details)
        return ok_result(f"qwen_tts {ver} + CUDA + model available", details)

    def load(self) -> None:
        if self._model is not None:
            return
        import torch
        dtype = getattr(torch, self.dtype.lower(), torch.bfloat16)
        started = time.perf_counter()
        self._model = self._model_cls.from_pretrained(
            self.model_id, device_map=self.device_map, dtype=dtype)
        print(f"[timing] tts_load={time.perf_counter() - started:.2f}s provider=qwen3-tts",
              flush=True)

    def unload(self) -> None:
        if self._model is None:
            return
        del self._model
        self._model = None
        import gc; gc.collect()

    def warm(self) -> None:
        fd, name = tempfile.mkstemp(prefix="echo-node-tts-warm-", suffix=".wav")
        os.close(fd)
        path = Path(name)
        try:
            self.synthesize_to_wav("Ready.", path)
        finally:
            path.unlink(missing_ok=True)

    def synthesize_to_wav(self, text: str, path: Path) -> Path:
        import soundfile as sf
        self.load()
        assert self._model is not None
        started = time.perf_counter()
        # UNVERIFIED kwarg surface (not exercised without GPU): per upstream
        # docs, generate_custom_voice(text, language, speaker, instruct=...)
        # returns (list[np.ndarray], sample_rate).
        wavs, sr = self._model.generate_custom_voice(
            text=text, language=self.language, speaker=self.speaker,
            instruct=self.instruct)
        sf.write(str(path), wavs[0], sr)
        print(f"[timing] tts_gen={time.perf_counter() - started:.2f}s provider=qwen3-tts",
              flush=True)
        return path

    @property
    def sample_rate(self) -> int:
        return self._sample_rate


class VoxCPMTTS(TTSProvider):
    """Expressive-prosody TTS via VoxCPM-0.5B (OpenBMB, Apache-2.0).

    API surface written against the documented upstream package (verified
    2026-10-01 against OpenBMB/VoxCPM and the openlark skill card):

        from voxcpm import VoxCPM                # pip package ``voxcpm``
        model = VoxCPM.from_pretrained("openbmb/VoxCPM", load_denoiser=False)
        wav = model.generate(text="Hello", cfg_value=2.0, inference_timesteps=10)
        sf.write("out.wav", wav, model.tts_model.sample_rate)
        # cloning: model.generate(text, reference_wav_path="voice.wav")

    The exact HF id for the 0.5B checkpoint is UNVERIFIED — ``openbmb/VoxCPM``
    is a guess; the verified id is ``openbmb/VoxCPM2`` (2B). Override via
    ``model_id`` in config. Synthesis kwargs were not exercised on this VM.
    """
    def __init__(self, config: dict[str, Any]):
        # Presence check only (matches the DotsTTS/CosyVoice3TTS pattern):
        # the model itself loads lazily in load().
        from voxcpm import VoxCPM as _VoxCPM
        self._model_cls = _VoxCPM
        self.model_id = str(config.get("model_id", "openbmb/VoxCPM"))
        self.cfg_value = float(config.get("cfg_value", 2.0))
        self.inference_timesteps = int(config.get("inference_timesteps", 10))
        self.reference_wav_path = config.get("reference_wav_path")
        self.prompt_wav_path = config.get("prompt_wav_path")
        self.prompt_text = config.get("prompt_text")
        self._model = None

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(
            name="voxcpn",
            version="0.5B",
            languages=["zh", "en"],  # 0.5B checkpoint is zh/en per upstream
            streaming=True,   # exposes generate_streaming()
            vram_gb=5.0,      # ~5GB per upstream reports — unverified here
            gpu_required=True,
            license="Apache-2.0",
            network=False,
            notes=("expressive prosody tier; 0.5B HF id unverified "
                   "(openbmb/VoxCPM2 is the verified 2B id); experimental"),
        )

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        found, ver = check_module("voxcpm")
        if not found:
            return missing_result("voxcpm",
                                   {"module": "voxcpm (pip install voxcpm)"})
        cuda_ok, cuda_info = check_cuda()
        cfg = config or {}
        model_id = str(cfg.get("model_id", "openbmb/VoxCPM"))
        details: dict[str, Any] = {"module_version": ver, "cuda": cuda_info,
                                   "model_id": model_id}
        problems = []
        if not cuda_ok:
            problems.append(f"CUDA: {cuda_info}")
        if Path(model_id).exists() or model_id.startswith((".", "/")):
            missing = check_paths(model_id)
            details["local_model_dir"] = model_id
            if missing:
                problems.append(f"local model dir missing: {model_id}")
        else:
            details["note"] = "HF model id — from_pretrained() would download; never in validate()"
        if problems:
            return ValidationResult(False, "; ".join(problems), details)
        return ok_result(f"voxcpm {ver} + CUDA + model available", details)

    def load(self) -> None:
        if self._model is not None:
            return
        started = time.perf_counter()
        self._model = self._model_cls.from_pretrained(self.model_id, load_denoiser=False)
        print(f"[timing] tts_load={time.perf_counter() - started:.2f}s provider=voxcpn",
              flush=True)

    def unload(self) -> None:
        if self._model is None:
            return
        del self._model
        self._model = None
        import gc; gc.collect()

    def warm(self) -> None:
        fd, name = tempfile.mkstemp(prefix="echo-node-tts-warm-", suffix=".wav")
        os.close(fd)
        path = Path(name)
        try:
            self.synthesize_to_wav("Ready.", path)
        finally:
            path.unlink(missing_ok=True)

    def synthesize_to_wav(self, text: str, path: Path) -> Path:
        import soundfile as sf
        self.load()
        assert self._model is not None
        started = time.perf_counter()
        # UNVERIFIED kwarg surface (not exercised without GPU): per upstream
        # docs, generate(text, cfg_value, inference_timesteps, ...) returns a
        # numpy wav; sample rate at model.tts_model.sample_rate.
        kwargs: dict[str, Any] = {"text": text, "cfg_value": self.cfg_value,
                                  "inference_timesteps": self.inference_timesteps}
        if self.reference_wav_path:
            kwargs["reference_wav_path"] = self.reference_wav_path
        if self.prompt_wav_path:
            kwargs["prompt_wav_path"] = self.prompt_wav_path
        if self.prompt_text:
            kwargs["prompt_text"] = self.prompt_text
        wav = self._model.generate(**kwargs)
        sf.write(str(path), wav, self._model.tts_model.sample_rate)
        print(f"[timing] tts_gen={time.perf_counter() - started:.2f}s provider=voxcpn",
              flush=True)
        return path

    def generate_stream(self, text: str):
        self.load()
        assert self._model is not None
        return self._model.generate_streaming(text)

    @property
    def sample_rate(self) -> int:
        if self._model is not None:
            return int(self._model.tts_model.sample_rate)
        return 16000  # 0.5B checkpoint is 16 kHz per upstream


class EspeakTTS(TTSProvider):
    def __init__(self, config: dict[str, Any]):
        self.voice = str(config.get("espeak_voice", "en-us"))
        self.speed = str(config.get("espeak_speed", 165))
        self.pitch = str(config.get("espeak_pitch", 45))
        if shutil.which("espeak-ng") is None:
            raise RuntimeError("espeak-ng is not installed.")

    def load(self) -> None:
        # No model to load (subprocess per synthesis); no-op so the class
        # satisfies the TTSProvider ABC. (Phase C fix: the Phase-A ABC
        # migration left this method out, which made EspeakTTS abstract
        # and broke create_tts()'s historical espeak-ng fallback.)
        return

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(
            name="espeak-ng",
            version="unknown",
            languages=["en"],  # other languages via the espeak_voice setting
            streaming=False,
            gpu_required=False,
            license="GPL-3.0",
            network=False,
            notes="CPU fallback TTS; robotic but always available",
        )

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        found, path = check_binary("espeak-ng")
        if found:
            return ok_result("espeak-ng present", {"path": path})
        return missing_result("espeak-ng", {"binary": "espeak-ng"})

    def synthesize_to_wav(self, text: str, path: Path) -> Path:
        subprocess.run(
            ["espeak-ng", "-v", self.voice, "-s", self.speed, "-p", self.pitch, "-w", str(path), text],
            check=True,
        )
        return path

    def unload(self) -> None:
        pass

    def warm(self) -> None:
        return


# ── Registry-backed factory (historical fallback behavior preserved) ──

def create_tts(tts_config: dict[str, Any]) -> TTSProvider:
    """Instantiate the configured TTS provider.

    Mirrors the old dispatch exactly: dots/cosyvoice3/kokoro by name,
    anything else → espeak-ng; a provider that fails to construct falls
    back to espeak-ng with the same log line as before.
    """
    from echo_node.slots import SlotType
    from echo_node.slots.registry import get_registry
    provider = str(tts_config.get("provider", "kokoro"))
    try:
        cls = get_registry().get(SlotType.TTS, provider)
    except KeyError:
        cls = EspeakTTS  # old `else:` branch — no warning, same as before
    try:
        return cls(tts_config)
    except Exception as exc:
        print(f"[tts] {provider} unavailable, falling back to espeak-ng: {exc}", flush=True)
        return EspeakTTS(tts_config)
