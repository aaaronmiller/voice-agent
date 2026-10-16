import sounddevice as sd
import soundfile as sf
import numpy as np
from pathlib import Path
from logger import setup_logger

logger = setup_logger(__name__)

class AudioRecorder:
    def __init__(self, sample_rate=16000, audio_dir=None):
        """Initialize audio recorder

        Args:
            sample_rate: Sample rate in Hz (default 16000 for Whisper)
            audio_dir: Directory to save recordings (default: project folder)
        """
        self.sample_rate = sample_rate
        self.audio_dir = Path(audio_dir) if audio_dir else Path(__file__).parent / "temp_audio"
        self.audio_dir.mkdir(exist_ok=True)

        self.recording = None
        self.stream = None
        self.audio_data = []

        logger.info(f"AudioRecorder initialized (sample_rate={sample_rate}Hz)")

    def start_recording(self):
        """Start recording from default microphone"""
        try:
            logger.info("Starting audio recording...")
            self.audio_data = []

            # Create stream for recording
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype='float32',
                callback=self._audio_callback,
                blocksize=4096
            )
            self.stream.start()
            logger.info("Recording started")
            return True
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            return False

    def _audio_callback(self, indata, frames, time_info, status):
        """Callback for audio stream"""
        if status:
            logger.warning(f"Audio stream status: {status}")
        self.audio_data.append(indata.copy())

    def stop_recording(self):
        """Stop recording and save to file"""
        try:
            if self.stream is None:
                logger.warning("No active recording")
                return None

            self.stream.stop()
            self.stream.close()
            logger.info("Recording stopped")

            # Combine audio data
            if not self.audio_data:
                logger.warning("No audio data recorded")
                return None

            audio = np.concatenate(self.audio_data, axis=0)

            # Save to temp file
            temp_file = self.audio_dir / "temp_recording.wav"
            sf.write(str(temp_file), audio, self.sample_rate)

            duration = len(audio) / self.sample_rate
            logger.info(f"Audio saved: {temp_file} ({duration:.1f}s)")

            return str(temp_file)
        except Exception as e:
            logger.error(f"Failed to stop recording: {e}")
            return None

    def get_recording_path(self):
        """Get path to temp recording"""
        return str(self.audio_dir / "temp_recording.wav")
