"""
Silero-VAD Provider

Voice Activity Detection using Silero-VAD model.
Lightweight, accurate, MIT licensed.
"""

import numpy as np

try:
    import torch

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

from worker.providers.base import VADProvider


class SileroVAD(VADProvider):
    """
    Silero Voice Activity Detection.

    Features:
    - Lightweight (~50MB VRAM)
    - Real-time capable
    - High accuracy
    - MIT license
    """

    def __init__(self):
        self._model = None
        self._get_speech_timestamps = None
        self._threshold = 0.5
        self._sample_rate = 16000
        self._window_size_samples = 512

    @property
    def vram_requirement_mb(self) -> int:
        return 50 if TORCH_AVAILABLE else 0

    async def initialize(self, model_path: str = "", threshold: float = 0.5) -> None:
        """Initialize Silero-VAD model."""
        if not TORCH_AVAILABLE:
            print("[SileroVAD] PyTorch not available, using energy-based fallback")
            self._threshold = threshold
            return

        self._threshold = threshold

        try:
            # Load model from torch hub
            self._model = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                trust_repo=True,
            )
            self._model.set_sample_rate(self._sample_rate)
            print(f"[SileroVAD] Model loaded, threshold: {threshold}")
        except Exception as e:
            print(f"[SileroVAD] Failed to load model: {e}, using energy-based fallback")
            self._model = None

    def is_speech(self, audio_chunk: np.ndarray) -> bool:
        """Check if audio chunk contains speech."""
        if self._model is None:
            return self._energy_based_detection(audio_chunk)

        try:
            audio_tensor = torch.from_numpy(audio_chunk).float()
            with torch.no_grad():
                speech_prob = self._model(audio_tensor, self._sample_rate).item()
            return speech_prob > self._threshold
        except Exception:
            return self._energy_based_detection(audio_chunk)

    def _energy_based_detection(self, audio_chunk: np.ndarray) -> bool:
        """Simple energy-based speech detection (fallback)."""
        rms = np.sqrt(np.mean(audio_chunk**2))
        return rms > 0.02

    async def shutdown(self) -> None:
        """Release resources."""
        self._model = None
        print("[SileroVAD] Shutdown complete")
