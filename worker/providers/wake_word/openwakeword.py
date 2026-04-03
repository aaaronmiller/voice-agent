"""
OpenWakeWord Provider

Wake word detection using OpenWakeWord.
Custom keyword training, Apache 2.0 licensed.
"""

import numpy as np

try:
    from openwakeword.model import Model
    OPENWAKEWORD_AVAILABLE = True
except ImportError:
    OPENWAKEWORD_AVAILABLE = False

from worker.providers.base import WakeWordProvider


class OpenWakeWordProvider(WakeWordProvider):
    """
    OpenWakeWord wake word detection.
    
    Features:
    - Custom keyword training
    - Low false positive rate
    - Real-time capable
    - Apache 2.0 license
    """

    def __init__(self):
        self._model = None
        self._threshold = 0.5
        self._wakeword_name = "yo_gimp"
        self._cooldown_ms = 2000
        self._last_detection_time = 0

    @property
    def vram_requirement_mb(self) -> int:
        """
        Estimated VRAM requirement.
        
        Returns:
            VRAM in MB (~100MB for OpenWakeWord)
        """
        return 100 if OPENWAKEWORD_AVAILABLE else 0

    async def initialize(self, model_path: str = "", threshold: float = 0.5) -> None:
        """
        Initialize OpenWakeWord model.
        
        Args:
            model_path: Path to .onnx model file or model name
            threshold: Detection threshold (0.0-1.0)
        """
        self._threshold = threshold
        
        if not OPENWAKEWORD_AVAILABLE:
            print("[OpenWakeWord] Library not installed, using placeholder")
            return
        
        # Load model
        # If model_path is a directory, look for .onnx files
        # If it's a name, use built-in models
        
        wakeword_models = [model_path] if model_path else []
        
        self._model = Model(
            wakeword_models=wakeword_models,
            inference_framework="onnx"  # or 'tflite'
        )
        
        print(f"[OpenWakeWord] Initialized with model: {model_path or 'default'}, threshold: {threshold}")

    def detect(self, audio_chunk: np.ndarray) -> bool:
        """
        Check if wake word detected in chunk.
        
        Args:
            audio_chunk: Audio data (int16 or float32, 16kHz)
        
        Returns:
            True if wake word detected
        """
        if not OPENWAKEWORD_AVAILABLE or self._model is None:
            # Placeholder: always return False
            return False
        
        # Ensure correct format (OpenWakeWord expects int16)
        if audio_chunk.dtype == np.float32:
            audio_chunk = (audio_chunk * 32767).astype(np.int16)
        
        # Run prediction
        self._model.predict(audio_chunk)
        
        # Check prediction buffer for wakeword
        for mdl in self._model.prediction_buffer.keys():
            if self._model.prediction_buffer[mdl][-1] > self._threshold:
                # Reset after detection
                self._model.reset()
                return True
        
        return False

    def set_threshold(self, threshold: float) -> None:
        """
        Update detection threshold.
        
        Args:
            threshold: New threshold (0.0-1.0)
        """
        self._threshold = threshold

    def set_cooldown(self, cooldown_ms: int) -> None:
        """
        Set cooldown period after detection.
        
        Args:
            cooldown_ms: Cooldown in milliseconds
        """
        self._cooldown_ms = cooldown_ms

    async def shutdown(self) -> None:
        """Release resources."""
        self._model = None
        print("[OpenWakeWord] Shutdown complete")
