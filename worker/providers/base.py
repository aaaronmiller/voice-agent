"""
Provider Abstract Base Classes for Echo-Node Pipeline

All STT, TTS, VAD, WakeWord, and LLM providers MUST implement these ABCs.
Adding a new provider means subclassing the appropriate ABC and registering
in the PROVIDER_REGISTRY.
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator
import numpy as np


class STTProvider(ABC):
    """Speech-to-Text provider interface."""

    @abstractmethod
    async def initialize(self, model_path: str, device: str = "cuda") -> None:
        """Load model into memory."""
        pass

    @abstractmethod
    async def transcribe_stream(self, audio_chunks: AsyncIterator[np.ndarray]) -> AsyncIterator[str]:
        """Stream audio chunks, yield partial transcripts."""
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Release model resources."""
        pass

    @property
    @abstractmethod
    def vram_requirement_mb(self) -> int:
        """VRAM needed by this provider's current model."""
        pass


class TTSProvider(ABC):
    """Text-to-Speech provider interface."""

    @abstractmethod
    async def initialize(self, model_path: str, voice: str, device: str = "cuda") -> None:
        """Load model into memory."""
        pass

    @abstractmethod
    async def synthesize(self, text: str) -> np.ndarray:
        """Synthesize full text to audio array (16kHz mono float32)."""
        pass

    @abstractmethod
    async def synthesize_stream(self, text: str) -> AsyncIterator[np.ndarray]:
        """Stream audio chunks as they're generated."""
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Release model resources."""
        pass

    @property
    @abstractmethod
    def vram_requirement_mb(self) -> int:
        """VRAM needed by this provider's current model."""
        pass


class VADProvider(ABC):
    """Voice Activity Detection provider interface."""

    @abstractmethod
    async def initialize(self, model_path: str) -> None:
        """Load model."""
        pass

    @abstractmethod
    def is_speech(self, audio_chunk: np.ndarray) -> bool:
        """Returns True if audio chunk contains speech."""
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Release resources."""
        pass


class WakeWordProvider(ABC):
    """Wake Word Detection provider interface."""

    @abstractmethod
    async def initialize(self, model_path: str, threshold: float = 0.5) -> None:
        """Load wake word model."""
        pass

    @abstractmethod
    def detect(self, audio_chunk: np.ndarray) -> bool:
        """Returns True if wake word detected in chunk."""
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Release resources."""
        pass


class LLMProvider(ABC):
    """LLM provider interface."""

    @abstractmethod
    async def initialize(self, model: str, base_url: str, api_key: str = "") -> None:
        """Configure connection. api_key is optional (blank for Ollama, required for OpenRouter/OpenAI)."""
        pass

    @abstractmethod
    async def chat_stream(self, messages: list[dict], tools: list[dict] | None = None) -> AsyncIterator[str]:
        """Stream response tokens from LLM."""
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Cleanup."""
        pass
