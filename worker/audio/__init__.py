"""
Audio Module for Echo-Node

Microphone capture, speaker playback, and acoustic echo cancellation.
"""

from worker.audio.capture import AudioCapture
from worker.audio.playback import AudioPlayback
from worker.audio.echo_cancel import EchoCanceller

__all__ = ['AudioCapture', 'AudioPlayback', 'EchoCanceller']
