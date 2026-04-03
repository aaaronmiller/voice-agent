"""
Speaker Audio Playback for Echo-Node

Plays synthesized TTS audio through system speakers.
Supports muting during playback for MVP echo cancellation.
"""

import asyncio
from typing import Optional
import numpy as np

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False
    try:
        import pyaudio
        PYAUDIO_AVAILABLE = True
    except ImportError:
        PYAUDIO_AVAILABLE = False


class AudioPlayback:
    """
    Speaker audio playback for TTS output.
    
    Plays 16kHz mono audio with optional muting for echo cancellation.
    """

    def __init__(
        self,
        sample_rate: int = 24000,
        channels: int = 1,
        chunk_size: int = 512
    ):
        """
        Initialize audio playback.
        
        Args:
            sample_rate: Sample rate in Hz (default: 24000 for TTS)
            channels: Number of channels (default: 1 for mono)
            chunk_size: Samples per chunk for streaming playback
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self._stream = None
        self._playing = False
        self._muted = False

    async def initialize(self) -> None:
        """Initialize audio playback system."""
        if not SOUNDDEVICE_AVAILABLE and not PYAUDIO_AVAILABLE:
            raise RuntimeError(
                "No audio library available. Install sounddevice or PyAudio:\n"
                "  pip install sounddevice\n"
                "  # or\n"
                "  pip install PyAudio"
            )

    async def play(self, audio: np.ndarray, block: bool = True) -> None:
        """
        Play audio array through speakers.
        
        Args:
            audio: Audio data as numpy array (float32, -1.0 to 1.0)
            block: If True, wait until playback completes
        """
        if self._muted:
            return
        
        # Ensure correct sample rate
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        
        # Play audio
        if SOUNDDEVICE_AVAILABLE:
            sd.play(audio, self.sample_rate, blocking=block)
        elif PYAUDIO_AVAILABLE:
            self._pyaudio = pyaudio.PyAudio()
            stream = self._pyaudio.open(
                format=pyaudio.paFloat32,
                channels=self.channels,
                rate=self.sample_rate,
                output=True
            )
            
            # Play in chunks for large audio
            for i in range(0, len(audio), self.chunk_size):
                chunk = audio[i:i + self.chunk_size]
                stream.write(chunk.tobytes())
            
            stream.stop_stream()
            stream.close()
            self._pyaudio.terminate()

    async def play_stream(self) -> asyncio.Queue[np.ndarray]:
        """
        Create a streaming playback queue.
        
        Returns:
            Queue to push audio chunks for immediate playback
        """
        queue: asyncio.Queue[np.ndarray] = asyncio.Queue()
        
        async def stream_player():
            if SOUNDDEVICE_AVAILABLE:
                stream = sd.OutputStream(
                    samplerate=self.sample_rate,
                    channels=self.channels,
                    blocksize=self.chunk_size,
                    dtype=np.float32
                )
                stream.start()
                
                try:
                    while self._playing:
                        try:
                            chunk = await asyncio.wait_for(
                                queue.get(),
                                timeout=0.1
                            )
                            if not self._muted:
                                stream.write(chunk)
                        except asyncio.TimeoutError:
                            continue
                finally:
                    stream.stop()
                    stream.close()
            elif PYAUDIO_AVAILABLE:
                self._pyaudio = pyaudio.PyAudio()
                stream = self._pyaudio.open(
                    format=pyaudio.paFloat32,
                    channels=self.channels,
                    rate=self.sample_rate,
                    output=True,
                    frames_per_buffer=self.chunk_size
                )
                
                try:
                    while self._playing:
                        try:
                            chunk = await asyncio.wait_for(
                                queue.get(),
                                timeout=0.1
                            )
                            if not self._muted:
                                stream.write(chunk.tobytes())
                        except asyncio.TimeoutError:
                            continue
                finally:
                    stream.stop_stream()
                    stream.close()
                    self._pyaudio.terminate()
        
        self._playing = True
        asyncio.create_task(stream_player())
        return queue

    async def stop(self) -> None:
        """Stop any ongoing playback."""
        self._playing = False
        if SOUNDDEVICE_AVAILABLE:
            sd.stop()

    def mute(self) -> None:
        """Mute playback (echo cancellation MVP)."""
        self._muted = True

    def unmute(self) -> None:
        """Unmute playback."""
        self._muted = False

    def is_playing(self) -> bool:
        """Check if playback is active."""
        return self._playing and not self._muted

    def is_muted(self) -> bool:
        """Check if playback is muted."""
        return self._muted
