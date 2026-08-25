"""
Echo-Node Component Interfaces — Abstract Base Classes for all providers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, Any

import numpy as np


class STTProvider(ABC):
    """Speech-to-text provider interface."""
    
    @abstractmethod
    async def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        ...
    
    @abstractmethod
    async def load(self) -> None:
        ...
    
    @abstractmethod
    async def unload(self) -> None:
        ...


class TTSProvider(ABC):
    """Text-to-speech provider interface."""
    
    @abstractmethod
    async def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        ...
    
    @abstractmethod
    async def synthesize_stream(self, text: str) -> AsyncIterator[tuple[np.ndarray, int]]:
        ...
    
    @abstractmethod
    async def load(self) -> None:
        ...
    
    @abstractmethod
    async def unload(self) -> None:
        ...


class VADProvider(ABC):
    """Voice activity detection provider interface."""
    
    @abstractmethod
    def is_speech(self, audio: np.ndarray) -> bool:
        ...
    
    @abstractmethod
    def speech_score(self, audio: np.ndarray) -> float:
        ...


class WakeWordProvider(ABC):
    """Wake word detection provider interface."""
    
    @abstractmethod
    def detect(self, audio: np.ndarray) -> tuple[bool, str, float]:
        ...
    
    @abstractmethod
    def load(self) -> None:
        ...
    
    @abstractmethod
    def unload(self) -> None:
        ...
