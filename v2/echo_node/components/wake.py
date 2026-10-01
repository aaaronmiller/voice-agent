"""Wake-word detection via OpenWakeWord (ONNX)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from echo_node.slots import Capability, WakeWordProvider
from echo_node.slots.validation import (
    ValidationResult,
    check_module,
    check_paths,
    missing_result,
    ok_result,
)


# ── Wake detector ───────────────────────────────────────────────────

class WakeDetector(WakeWordProvider):
    def __init__(self, config: dict[str, Any]):
        self.enabled = bool(config.get("enabled", True))
        self.sensitivity = float(config.get("sensitivity", 0.35))
        self.model = None
        self.model_paths = [str(p) for p in config.get("model_paths", [])]
        if not self.enabled:
            return
        if not self.model_paths:
            import openwakeword
            from openwakeword.utils import download_models
            for name in config.get("pretrained", ["hey_jarvis"]):
                model_info = openwakeword.MODELS.get(str(name))
                if not model_info:
                    raise ValueError(f"Unknown OpenWakeWord pretrained model: {name}")
                download_models(model_names=[str(name)])
                self.model_paths.append(model_info["model_path"].replace(".tflite", ".onnx"))
        missing = [p for p in self.model_paths if not Path(p).exists()]
        if missing:
            raise FileNotFoundError(f"Wake-word model missing: {missing[0]}")
        from openwakeword.model import Model
        self.model = Model(wakeword_models=self.model_paths, inference_framework="onnx")

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(
            name="openwakeword",
            version="unknown",
            languages=[],  # wake phrases are language-agnostic acoustic models
            streaming=True,   # per-chunk detect()
            gpu_required=False,  # ONNX CPU
            license="Apache-2.0",
            network=False,
            notes="ONNX wake-word models; downloads pretrained models on first use",
        )

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        found, ver = check_module("openwakeword")
        if not found:
            return missing_result("openwakeword", {"module": "openwakeword"})
        cfg = config or {}
        paths = [str(p) for p in cfg.get("model_paths", [])]
        missing = check_paths(*paths)
        details = {"version": ver, "model_paths": paths}
        if missing:
            # Without configured model_paths the detector downloads
            # pretrained models at construction — that needs network and
            # is not something a validator may do. Report honestly.
            details["missing"] = missing
            return ValidationResult(
                False,
                f"configured wake model files missing: {missing[0]}",
                details,
            )
        if not paths:
            details["note"] = ("no model_paths configured; construction would "
                               "download pretrained models (network)")
        return ok_result(f"openwakeword {ver} importable", details)

    def detect(self, samples: np.ndarray) -> tuple[bool, str, float]:
        if not self.enabled:
            return True, "disabled", 1.0
        assert self.model is not None
        scores = self.model.predict(samples)
        if not scores:
            return False, "", 0.0
        name, score = max(scores.items(), key=lambda item: float(item[1]))
        score = float(score)
        return score >= self.sensitivity, name, score
