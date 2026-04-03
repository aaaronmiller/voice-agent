"""
Audio Module for Echo-Node

Microphone capture and speaker playback.
"""

from worker.audio.capture import AudioCapture
from worker.audio.playback import AudioPlayback

__all__ = ['AudioCapture', 'AudioPlayback']
