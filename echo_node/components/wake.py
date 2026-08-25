"""
Echo-Node Wake Word Components — OpenWakeWord detector.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


class WakeDetector:
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


# ── Silero VAD ──────────────────────────────────────────────────────