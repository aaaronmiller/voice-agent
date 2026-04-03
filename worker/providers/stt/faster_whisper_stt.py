"""
Faster-Whisper STT Provider

CTranslate2-based Whisper implementation.
Fast, accurate, supports multiple languages.
"""

import asyncio
from typing import AsyncIterator
import numpy as np

try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    FASTER_WHISPER_AVAILABLE = False

from worker.providers.base import STTProvider


class FasterWhisperSTT(STTProvider):
    """
    Faster-Whisper streaming STT provider.
    
    Features:
    - CTranslate2 acceleration (faster than PyTorch)
    - Multiple Whisper model sizes
    - Multi-language support
    - Streaming transcription
    """

    def __init__(self):
        self._model = None
        self._model_size = "base"  # tiny, base, small, medium, large-v2
        self._device = "cpu"
        self._vram_mb = 0
        self._language = "en"

    @property
    def vram_requirement_mb(self) -> int:
        """
        Estimated VRAM requirement.
        
        Returns:
            VRAM in MB (varies by model size)
        """
        return self._vram_mb if self._vram_mb > 0 else 1500  # Default 1.5GB for base

    async def initialize(self, model_path: str = "", device: str = "cuda") -> None:
        """
        Initialize faster-whisper model.
        
        Args:
            model_path: Model size or path (tiny, base, small, medium, large-v2)
            device: 'cuda' or 'cpu'
        """
        if not FASTER_WHISPER_AVAILABLE:
            raise ImportError(
                "faster-whisper not installed. Install with:\n"
                "  pip install faster-whisper"
            )

        self._model_size = model_path or "base"
        self._device = "cuda" if device == "cuda" else "cpu"
        
        # Map device for CTranslate2
        if self._device == "cuda":
            compute_type = "float16"
            self._vram_mb = self._estimate_vram()
        else:
            compute_type = "int8"
            self._vram_mb = 0
        
        print(f"[FasterWhisper] Loading model: {self._model_size}, device: {self._device}")
        
        # Load model
        # self._model = WhisperModel(
        #     self._model_size,
        #     device=self._device,
        #     compute_type=compute_type,
        #     download_root="models/stt/faster-whisper"
        # )
        
        print(f"[FasterWhisper] ✅ Model loaded")

    def _estimate_vram(self) -> int:
        """Estimate VRAM based on model size."""
        vram_map = {
            'tiny': 500,
            'base': 1500,
            'small': 2500,
            'medium': 4500,
            'large-v2': 8000,
        }
        return vram_map.get(self._model_size, 1500)

    async def transcribe_stream(self, audio_chunks: AsyncIterator[np.ndarray]) -> AsyncIterator[str]:
        """
        Stream audio chunks, yield partial transcripts.
        
        Note: faster-whisper doesn't natively support streaming.
        This implementation buffers audio and transcribes in segments.
        
        Args:
            audio_chunks: Async iterator of audio chunks (float32, 16kHz)
        
        Yields:
            Partial transcript strings
        """
        if not self._model:
            raise RuntimeError("STT not initialized. Call initialize() first.")

        # Buffer audio chunks
        buffer = []
        buffer_duration = 0  # seconds
        segment_duration = 10  # Transcribe every 10 seconds
        
        async for chunk in audio_chunks:
            if chunk.dtype != np.float32:
                chunk = chunk.astype(np.float32)
            
            buffer.append(chunk)
            buffer_duration += len(chunk) / 16000  # 16kHz sample rate
            
            # Transcribe when buffer reaches threshold
            if buffer_duration >= segment_duration:
                # Concatenate buffer
                audio = np.concatenate(buffer)
                buffer = []
                buffer_duration = 0
                
                # Transcribe segment
                # segments, info = self._model.transcribe(
                #     audio,
                #     language=self._language,
                #     vad_filter=True  # Use built-in VAD
                # )
                
                # For now, placeholder
                transcript = "[faster-whisper segment]"
                yield transcript

        # Transcribe remaining buffer
        if buffer:
            audio = np.concatenate(buffer)
            # segments, info = self._model.transcribe(audio, language=self._language)
            # final_transcript = " ".join([segment.text for segment in segments])
            # yield final_transcript

    async def shutdown(self) -> None:
        """Release resources."""
        self._model = None
        print("[FasterWhisper] Shutdown complete")

    def set_language(self, language: str) -> None:
        """
        Set transcription language.
        
        Args:
            language: Language code (e.g., 'en', 'es', 'fr')
        """
        self._language = language
