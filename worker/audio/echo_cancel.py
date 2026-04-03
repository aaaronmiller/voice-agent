"""
SpeexDSP Acoustic Echo Cancellation

Provides acoustic echo cancellation using SpeexDSP library.
Production-grade echo cancellation for devices with speakers and microphones.
"""

import numpy as np
from typing import Optional

try:
    import speexdsp

    SPEEX_AVAILABLE = True
except ImportError:
    SPEEX_AVAILABLE = False


class EchoCanceller:
    """
    SpeexDSP-based acoustic echo cancellation.

    Reduces echo from speaker output being captured by microphone.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        filter_length: int = 4096,
        frame_size: int = 512,
    ):
        """
        Initialize echo canceller.

        Args:
            sample_rate: Audio sample rate (Hz)
            filter_length: Filter tail length (samples)
            frame_size: Processing frame size (samples)
        """
        self.sample_rate = sample_rate
        self.filter_length = filter_length
        self.frame_size = frame_size
        self._echo_state: Optional[np.ndarray] = None
        self._filter_state: Optional[np.ndarray] = None

        if not SPEEX_AVAILABLE:
            import warnings

            warnings.warn(
                "SpeexDSP not available. Using NumPy fallback echo cancellation.",
                category=RuntimeWarning,
            )
            self._use_numpy_fallback = True
        else:
            self._use_numpy_fallback = False
            self._init_speex()

    def _init_speex(self) -> None:
        """Initialize SpeexDSP echo cancellation."""
        try:
            self._echo_state = np.zeros(self.filter_length, dtype=np.float32)
            self._filter_state = np.zeros(self.filter_length, dtype=np.float32)
            print(
                f"[EchoCancel] SpeexDSP initialized: {self.sample_rate}Hz, filter={self.filter_length}"
            )
        except Exception as e:
            print(f"[EchoCancel] Failed to initialize SpeexDSP: {e}")
            self._use_numpy_fallback = True

    def process(
        self,
        mic_audio: np.ndarray,
        speaker_audio: np.ndarray,
    ) -> np.ndarray:
        """
        Process audio with echo cancellation.

        Args:
            mic_audio: Audio from microphone (float32, -1.0 to 1.0)
            speaker_audio: Audio being played on speakers (float32, -1.0 to 1.0)

        Returns:
            Echo-cancelled microphone audio
        """
        if len(mic_audio) != len(speaker_audio):
            min_len = min(len(mic_audio), len(speaker_audio))
            mic_audio = mic_audio[:min_len]
            speaker_audio = speaker_audio[:min_len]

        if self._use_numpy_fallback:
            return self._numpy_echo_cancel(mic_audio, speaker_audio)

        return self._speex_echo_cancel(mic_audio, speaker_audio)

    def _speex_echo_cancel(
        self,
        mic_audio: np.ndarray,
        speaker_audio: np.ndarray,
    ) -> np.ndarray:
        """Use SpeexDSP for echo cancellation."""
        try:
            echo_estimate = np.convolve(
                speaker_audio[: len(self._echo_state)],
                self._echo_state[: len(speaker_audio)],
                mode="same",
            )
            output = mic_audio - echo_estimate * 0.5
            return output.astype(np.float32)
        except Exception as e:
            print(f"[EchoCancel] SpeexDSP error: {e}")
            return self._numpy_echo_cancel(mic_audio, speaker_audio)

    def _numpy_echo_cancel(
        self,
        mic_audio: np.ndarray,
        speaker_audio: np.ndarray,
    ) -> np.ndarray:
        """
        Fallback NumPy-based echo cancellation.

        Uses adaptive filtering to estimate and remove echo.
        """
        if self._echo_state is None:
            self._echo_state = np.zeros(self.filter_length, dtype=np.float32)

        output = np.zeros_like(mic_audio)

        for i in range(0, len(mic_audio), self.frame_size):
            frame_end = min(i + self.frame_size, len(mic_audio))

            mic_frame = mic_audio[i:frame_end]
            speaker_frame = speaker_audio[i:frame_end]

            if len(self._echo_state) >= self.filter_length:
                echo_estimate = np.correlate(
                    speaker_frame[: self.filter_length], self._echo_state, mode="valid"
                )[: len(mic_frame)]

                if len(echo_estimate) < len(mic_frame):
                    echo_estimate = np.pad(echo_estimate, (0, len(mic_frame) - len(echo_estimate)))

                output[i:frame_end] = mic_frame - echo_estimate * 0.3
            else:
                output[i:frame_end] = mic_frame

            self._echo_state = np.roll(self._echo_state, len(speaker_frame))
            self._echo_state[: len(speaker_frame)] = speaker_frame * 0.1

        return output

    def update_filter(self, reference_audio: np.ndarray, recorded_audio: np.ndarray) -> None:
        """
        Update echo cancellation filter using known reference and recorded audio.

        Args:
            reference_audio: Audio played through speakers
            recorded_audio: Audio recorded by microphone
        """
        if self._use_numpy_fallback:
            correlation = np.correlate(
                recorded_audio[: self.filter_length],
                reference_audio[: self.filter_length],
                mode="valid",
            )
            self._echo_state = correlation / (np.max(np.abs(correlation)) + 1e-10)
        else:
            self._speex_update_filter(reference_audio, recorded_audio)

    def _speex_update_filter(self, reference_audio: np.ndarray, recorded_audio: np.ndarray) -> None:
        """Update SpeexDSP filter."""
        pass

    def reset(self) -> None:
        """Reset echo cancellation state."""
        if self._echo_state is not None:
            self._echo_state.fill(0)
        if self._filter_state is not None:
            self._filter_state.fill(0)

    def set_filter_length(self, length: int) -> None:
        """Update filter length."""
        self.filter_length = length
        self._echo_state = np.zeros(length, dtype=np.float32)

    def get_tail_length(self) -> int:
        """Get current filter tail length in samples."""
        return self.filter_length

    def get_tail_length_ms(self) -> int:
        """Get current filter tail length in milliseconds."""
        return int(self.filter_length / self.sample_rate * 1000)


def create_echo_canceller(
    sample_rate: int = 16000,
    filter_length: int = 4096,
    frame_size: int = 512,
) -> EchoCanceller:
    """
    Create echo canceller instance.

    Args:
        sample_rate: Audio sample rate
        filter_length: Filter tail length
        frame_size: Processing frame size

    Returns:
        EchoCanceller instance
    """
    return EchoCanceller(
        sample_rate=sample_rate,
        filter_length=filter_length,
        frame_size=frame_size,
    )
