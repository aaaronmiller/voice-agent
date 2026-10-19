"""STT backends: faster-whisper and Parakeet (via onnx-asr)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from echo_node.slots import Capability, STTProvider
from echo_node.slots.validation import (
    ValidationResult,
    check_module,
    missing_result,
    ok_result,
)


# ── STT backends ────────────────────────────────────────────────────

class FasterWhisperSTT(STTProvider):
    """STT via faster-whisper (CTranslate2, CPU int8)."""
    def __init__(self, config: dict[str, Any]):
        self.model_size = str(config.get("model", "tiny"))
        self.device = str(config.get("device", "cpu"))
        self.compute_type = str(config.get("compute_type", "int8"))
        self._model = None

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(
            name="faster-whisper",
            version="unknown",
            languages=["en"],  # transcribe() pins language="en"
            streaming=False,    # batch: whole WAV per transcribe() call
            vram_gb=None,
            gpu_required=False,  # CTranslate2 CPU int8
            license="MIT",
            network=False,
            notes="model downloads from Hugging Face on first load",
        )

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        found, ver = check_module("faster_whisper")
        if found:
            return ok_result(f"faster-whisper {ver} importable", {"version": ver})
        return missing_result("faster-whisper", {"module": "faster_whisper"})

    def load(self) -> None:
        if self._model is not None:
            return
        from faster_whisper import WhisperModel
        started = time.perf_counter()
        print(f"[stt] loading faster-whisper {self.model_size} ({self.device}, {self.compute_type})", flush=True)
        self._model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
        print(f"[timing] stt_load={time.perf_counter() - started:.2f}s", flush=True)

    def unload(self) -> None:
        if self._model is None:
            return
        del self._model
        self._model = None
        import gc; gc.collect()

    def transcribe(self, wav_path: Path) -> str:
        self.load()
        assert self._model is not None
        started = time.perf_counter()
        segments, info = self._model.transcribe(str(wav_path), language="en")
        text = " ".join(s.text.strip() for s in segments).strip()
        print(f"[timing] stt={time.perf_counter() - started:.2f}s", flush=True)
        return text


# Parakeet TDT v3 0.6B — drop-in upgrade over v2 (better accuracy, true
# streaming, INT8 bundle ~640MB). onnx-asr auto-downloads the HF model id.
PARAKEET_V3_MODEL = "istupakov/parakeet-tdt-0.6b-v3-onnx"
# Fallback if the v3 bundle can't be downloaded or loaded.
PARAKEET_V2_MODEL = "nemo-parakeet-tdt-0.6b-v2"


class ParakeetSTT(STTProvider):
    def __init__(self, config: dict[str, Any]):
        self.model_name = str(config.get("model_name", PARAKEET_V3_MODEL))
        self.quantization = str(config.get("quantization", "int8"))
        self.providers = [str(p) for p in config.get("providers", [])]
        self.model = None

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(
            name="parakeet",
            version="0.6B (TDT v3)",
            languages=["en"],
            streaming=True,   # TDT is a streaming-capable architecture
            vram_gb=0.7,      # INT8 ONNX bundle ~640MB
            gpu_required=False,  # CPUExecutionProvider default
            license="unknown",   # v3 ONNX bundle license unverified; NVIDIA's
                                 # v2 weights are non-commercial (CC-BY-NC-4.0)
            network=True,        # onnx-asr auto-downloads the HF model id
            notes=("default STT; auto-falls back to nemo-parakeet-tdt-0.6b-v2 "
                   "if the v3 bundle fails to load"),
        )

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        found, ver = check_module("onnx_asr")
        if found:
            return ok_result(f"onnx-asr {ver} importable", {"version": ver})
        return missing_result("onnx-asr", {"module": "onnx_asr"})

    def load(self) -> None:
        if self.model is not None:
            return
        import onnx_asr
        providers = self.providers or ["CPUExecutionProvider"]
        started = time.perf_counter()
        print(f"[stt] loading {self.model_name} ({self.quantization}) providers={providers}", flush=True)
        try:
            self.model = onnx_asr.load_model(self.model_name, quantization=self.quantization, providers=providers)
        except Exception as exc:
            # Only auto-fallback when the caller didn't pin a custom model:
            # the v3 default failing shouldn't brick STT if v2 still works.
            if self.model_name == PARAKEET_V3_MODEL:
                print(f"[stt] v3 model failed ({exc}); falling back to {PARAKEET_V2_MODEL}", flush=True)
                self.model_name = PARAKEET_V2_MODEL
                self.model = onnx_asr.load_model(self.model_name, quantization=self.quantization, providers=providers)
            else:
                raise
        print(f"[timing] stt_load={time.perf_counter() - started:.2f}s", flush=True)

    def unload(self) -> None:
        if self.model is None:
            return
        del self.model
        self.model = None
        import gc; gc.collect()

    def transcribe(self, wav_path: Path) -> str:
        self.load()
        assert self.model is not None
        started = time.perf_counter()
        result = self.model.recognize(str(wav_path))
        text = result[0] if isinstance(result, list) else result
        print(f"[timing] stt={time.perf_counter() - started:.2f}s", flush=True)
        return str(text).strip()


class HuggingFaceWhisperSTT(STTProvider):
    """STT via HuggingFace transformers Whisper (CPU, no CTranslate2 needed).

    Registered through the same ``register_builtin`` path as the other
    providers. Proven 2026-10-17 on SPECTRE-16 (Windows 11, torch CPU):
    whisper-tiny loads in ~3s, transcribes 3s audio in ~1.6s. Default
    transcriber for the Windows dictation path (T011).
    """
    def __init__(self, config: dict[str, Any]):
        self.model_id = str(config.get("model_id", "openai/whisper-tiny"))
        self.language = str(config.get("language", "en"))
        self._processor = None
        self._model = None

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(
            name="hf-whisper",
            version="whisper-tiny",
            languages=["en"],
            streaming=False,  # batch: whole WAV per transcribe() call
            vram_gb=None,
            gpu_required=False,  # torch CPU
            license="MIT",
            network=True,  # HF download on first load
            notes="transformers Whisper tiny; CPU transcription",
        )

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        found, ver = check_module("transformers")
        if found:
            return ok_result(f"transformers {ver} importable", {"version": ver})
        return missing_result("transformers", {"module": "transformers"})

    def load(self) -> None:
        if self._model is not None:
            return
        import torch
        from transformers import WhisperForConditionalGeneration, WhisperProcessor
        started = time.perf_counter()
        print(f"[stt] loading {self.model_id} (torch CPU)", flush=True)
        self._processor = WhisperProcessor.from_pretrained(self.model_id)
        self._model = WhisperForConditionalGeneration.from_pretrained(self.model_id)
        self._model = self._model.to(torch.device("cpu"))
        self._model.eval()
        print(f"[timing] stt_load={time.perf_counter() - started:.2f}s", flush=True)

    def unload(self) -> None:
        if self._model is None:
            return
        del self._model
        del self._processor
        self._model = None
        self._processor = None
        import gc; gc.collect()

    def transcribe(self, wav_path: Path) -> str:
        self.load()
        assert self._model is not None and self._processor is not None
        started = time.perf_counter()
        try:
            import soundfile as sf
            audio, sr = sf.read(str(wav_path), dtype="float32")
            if sr != 16000:
                import numpy as np
                ratio = 16000 / float(sr)
                idx = (np.arange(int(len(audio) * ratio)) / ratio).astype(int)
                audio = np.asarray(audio)[idx.clip(0, len(audio) - 1)]
        except ImportError:
            import wave as _wave
            import numpy as _np
            with _wave.open(str(wav_path), "rb") as wf:
                raw = wf.readframes(wf.getnframes())
            audio = _np.frombuffer(raw, dtype=_np.int16).astype(_np.float32) / 32768.0
        inputs = self._processor(audio, sampling_rate=16000, return_tensors="pt").input_features
        ids = self._model.generate(inputs, max_new_tokens=128, language=self.language)
        text = self._processor.batch_decode(ids, skip_special_tokens=True)[0]
        print(f"[timing] stt={time.perf_counter() - started:.2f}s", flush=True)
        return str(text).strip()


# ── Registry-backed factory (historical fallback behavior preserved) ──

def create_stt(stt_config: dict[str, Any]) -> STTProvider:
    """Instantiate the configured STT provider.

    Unknown provider names fall back to ParakeetSTT — exactly the old
    ``if faster-whisper … else Parakeet`` dispatch in the orchestrator.
    """
    from echo_node.slots import SlotType
    from echo_node.slots.registry import get_registry
    provider = str(stt_config.get("provider", "parakeet"))
    try:
        cls = get_registry().get(SlotType.STT, provider)
    except KeyError:
        print(f"[stt] unknown provider {provider!r}, falling back to parakeet", flush=True)
        cls = ParakeetSTT
    return cls(stt_config)
