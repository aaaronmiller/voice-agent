"""
Microphone Audio Capture for Echo-Node

Captures audio from microphone at 16kHz mono using PyAudio or sounddevice.
Handles WSL2 PipeWire/PulseAudio auto-detection.
"""

import asyncio
import os
import shutil
from typing import AsyncIterator, Optional
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


class AudioCapture:
    """
    Microphone audio capture with WSL2 auto-detection.
    
    Captures 16kHz mono audio in chunks suitable for streaming STT.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_size: int = 512,
        device: Optional[str] = None
    ):
        """
        Initialize audio capture.
        
        Args:
            sample_rate: Sample rate in Hz (default: 16000)
            channels: Number of channels (default: 1 for mono)
            chunk_size: Samples per chunk (default: 512 = 32ms at 16kHz)
            device: Optional device name (default: system default)
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.device = device
        self._stream = None
        self._running = False

    def detect_audio_server(self) -> str:
        """
        Detect audio server for WSL2 configuration.
        
        Returns:
            'pipewire', 'pulseaudio', or 'unknown'
        """
        if shutil.which('pw-cli'):
            return 'pipewire'
        elif shutil.which('pactl'):
            return 'pulseaudio'
        return 'unknown'

    def configure_wsl2(self) -> None:
        """
        Configure audio for WSL2 environment.
        
        Sets environment variables for PipeWire/PulseAudio.
        """
        server = self.detect_audio_server()
        
        if server == 'pipewire':
            os.environ.setdefault('PIPEWIRE_REMOTE', 'default')
        elif server == 'pulseaudio':
            # WSL2 typically uses PulseAudio over TCP
            os.environ.setdefault('PULSE_SERVER', '127.0.0.1')
        
        # Set default device if specified
        if self.device:
            if SOUNDDEVICE_AVAILABLE:
                sd.default.device = self.device

    async def initialize(self) -> None:
        """Initialize audio capture system."""
        if not SOUNDDEVICE_AVAILABLE and not PYAUDIO_AVAILABLE:
            raise RuntimeError(
                "No audio library available. Install sounddevice or PyAudio:\n"
                "  pip install sounddevice\n"
                "  # or\n"
                "  pip install PyAudio"
            )
        
        # Auto-detect WSL2
        if 'WSL' in os.uname().release:
            self.configure_wsl2()
        
        # List available devices for debugging
        if SOUNDDEVICE_AVAILABLE:
            devices = sd.query_devices()
            print(f"Audio devices: {len(devices)} found")
            for i, dev in enumerate(devices):
                if dev['max_input_channels'] > 0:
                    print(f"  Input {i}: {dev['name']}")

    def get_default_device(self) -> Optional[int]:
        """
        Get default input device index.
        
        Returns:
            Device index or None if using system default
        """
        if self.device and SOUNDDEVICE_AVAILABLE:
            try:
                devices = sd.query_devices()
                for i, dev in enumerate(devices):
                    if self.device.lower() in dev['name'].lower():
                        return i
            except Exception:
                pass
        return None

    async def start(self) -> None:
        """Start audio capture stream."""
        if self._running:
            return
        
        device_idx = self.get_default_device()
        
        if SOUNDDEVICE_AVAILABLE:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                blocksize=self.chunk_size,
                device=device_idx,
                dtype=np.float32
            )
            self._stream.start()
        elif PYAUDIO_AVAILABLE:
            self._pyaudio = pyaudio.PyAudio()
            self._stream = self._pyaudio.open(
                format=pyaudio.paFloat32,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size,
                input_device_index=device_idx
            )
        
        self._running = True

    async def stop(self) -> None:
        """Stop audio capture stream."""
        if not self._running:
            return
        
        if SOUNDDEVICE_AVAILABLE and self._stream:
            self._stream.stop()
            self._stream.close()
        elif PYAUDIO_AVAILABLE and self._stream:
            self._stream.stop_stream()
            self._stream.close()
            self._pyaudio.terminate()
        
        self._running = False
        self._stream = None

    async def read_chunk(self) -> np.ndarray:
        """
        Read a single audio chunk.
        
        Returns:
            Audio chunk as numpy array (float32, -1.0 to 1.0)
        """
        if not self._running:
            raise RuntimeError("Audio capture not started. Call start() first.")
        
        if SOUNDDEVICE_AVAILABLE and self._stream:
            chunk, _ = self._stream.read(self.chunk_size)
            return chunk.flatten().astype(np.float32)
        elif PYAUDIO_AVAILABLE and self._stream:
            data = self._stream.read(self.chunk_size, exception_on_overflow=False)
            return np.frombuffer(data, dtype=np.float32).flatten()
        else:
            raise RuntimeError("No audio stream available")

    async def capture_stream(self) -> AsyncIterator[np.ndarray]:
        """
        Async generator yielding audio chunks continuously.
        
        Yields:
            Audio chunks as numpy arrays until stopped
        """
        await self.start()
        try:
            while self._running:
                chunk = await self.read_chunk()
                yield chunk
        finally:
            await self.stop()

    def is_running(self) -> bool:
        """Check if audio capture is active."""
        return self._running
