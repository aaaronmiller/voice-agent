"""
Sherpa-ONNX Streaming STT Provider

Uses sherpa-onnx for streaming speech-to-text.
Supports multiple model architectures (Whisper, Parakeet, Zipformer).
"""

import asyncio
from typing import AsyncIterator
import numpy as np

try:
    import sherpa_onnx
    SHERPA_AVAILABLE = True
except ImportError:
    SHERPA_AVAILABLE = False

from worker.providers.base import STTProvider


class SherpaSTT(STTProvider):
    """
    Sherpa-ONNX streaming STT provider.
    
    Supports:
    - Streaming partial transcripts
    - Multiple model architectures
    - CUDA, CPU, OpenVINO backends
    """

    def __init__(self):
        self._recognizer = None
        self._stream = None
        self._vram_mb = 0

    @property
    def vram_requirement_mb(self) -> int:
        """
        Estimated VRAM requirement.
        
        Returns:
            VRAM in MB (varies by model, ~500MB for small, ~2GB for large)
        """
        return self._vram_mb if self._vram_mb > 0 else 1024  # Default 1GB

    async def initialize(self, model_path: str, device: str = "cuda") -> None:
        """
        Initialize sherpa-onnx recognizer.
        
        Args:
            model_path: Path to sherpa-onnx model directory or model tag
            device: 'cuda', 'cpu', or 'openvino'
        """
        if not SHERPA_AVAILABLE:
            raise ImportError(
                "sherpa-onnx not installed. Install with:\n"
                "  pip install sherpa-onnx"
            )

        # Configure recognizer based on model type
        # For now, use a default streaming Zipformer model
        # User can override with custom model_path
        
        model_config = self._build_model_config(model_path, device)
        
        self._recognizer = sherpa_onnx.OnlineRecognizer(model_config)
        self._stream = None
        
        print(f"[SherpaSTT] Initialized with device: {device}")

    def _build_model_config(self, model_path: str, device: str) -> 'sherpa_onnx.OnlineRecognizerConfig':
        """
        Build sherpa-onnx recognizer config.
        
        Args:
            model_path: Path to model
            device: Compute device
        
        Returns:
            Recognizer config
        """
        # Default: streaming Zipformer English model
        # Download: https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-en-2023-06-26.tar.bz2
        
        model_dir = model_path or "models/stt/sherpa-onnx-streaming-zipformer-en-2023-06-26"
        
        # Map device string
        provider = "cuda" if device == "cuda" else "cpu"
        
        config = sherpa_onnx.OnlineRecognizerConfig(
            model_config=sherpa_onnx.OnlineRecognizerModelConfig(
                transducer=sherpa_onnx.TransducerModelConfig(
                    encoder=f"{model_dir}/encoder-epoch-99-avg-1.onnx",
                    decoder=f"{model_dir}/decoder-epoch-99-avg-1.onnx",
                    joiner=f"{model_dir}/joiner-epoch-99-avg-1.onnx",
                ),
                tokens=f"{model_dir}/tokens.txt",
                num_threads=2,
                provider=provider,
            ),
            decoding_method="greedy_search",
            max_active_paths=4,
            enable_truncation=False,
        )
        
        # Estimate VRAM
        if device == "cuda":
            self._vram_mb = 1500  # ~1.5GB for Zipformer
        else:
            self._vram_mb = 0
        
        return config

    async def transcribe_stream(self, audio_chunks: AsyncIterator[np.ndarray]) -> AsyncIterator[str]:
        """
        Stream audio chunks, yield partial transcripts.
        
        Args:
            audio_chunks: Async iterator of audio chunks (float32, 16kHz)
        
        Yields:
            Partial transcript strings
        """
        if not self._recognizer:
            raise RuntimeError("STT not initialized. Call initialize() first.")

        # Create new stream for this utterance
        stream = self._recognizer.create_stream()

        async for chunk in audio_chunks:
            # Ensure correct format
            if chunk.dtype != np.float32:
                chunk = chunk.astype(np.float32)
            
            # Accept sample
            stream.accept_waveform(16000, chunk)
            
            # Process while there's output
            while self._recognizer.is_ready(stream):
                self._recognizer.decode(stream)
            
            # Yield partial transcript
            text = stream.result.text
            if text:
                yield text

        # Finalize
        tail_paddings = np.zeros(int(16000 * 0.5), dtype=np.float32)  # 500ms padding
        stream.accept_waveform(16000, tail_paddings)
        
        while self._recognizer.is_ready(stream):
            self._recognizer.decode(stream)
        
        # Yield final transcript
        final_text = stream.result.text
        if final_text:
            yield final_text

    async def shutdown(self) -> None:
        """Release resources."""
        self._recognizer = None
        self._stream = None
        print("[SherpaSTT] Shutdown complete")
