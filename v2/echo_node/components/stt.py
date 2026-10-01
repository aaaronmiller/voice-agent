"""STT backends: faster-whisper and Parakeet (via onnx-asr)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any


# ── STT backends ────────────────────────────────────────────────────

class FasterWhisperSTT:
    """STT via faster-whisper (CTranslate2, CPU int8)."""
    def __init__(self, config: dict[str, Any]):
        self.model_size = str(config.get("model", "tiny"))
        self.device = str(config.get("device", "cpu"))
        self.compute_type = str(config.get("compute_type", "int8"))
        self._model = None

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


class ParakeetSTT:
    def __init__(self, config: dict[str, Any]):
        self.model_name = str(config.get("model_name", PARAKEET_V3_MODEL))
        self.quantization = str(config.get("quantization", "int8"))
        self.providers = [str(p) for p in config.get("providers", [])]
        self.model = None

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
