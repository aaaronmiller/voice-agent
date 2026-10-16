#!/usr/bin/env python3
"""
Hotkey-Triggered Speech-to-Text Background Service
Press Ctrl+Shift+A to record → Press again to stop and transcribe → Auto-paste result
"""

import json
import time
from pathlib import Path
from threading import Thread, Event
import sys

from logger import setup_logger
from hotkey_listener import HotkeyListener
from audio_recorder import AudioRecorder
from stt_engine import STTEngine
from clipboard_manager import ClipboardManager
from paster import Paster

logger = setup_logger(__name__)

class STTService:
    def __init__(self, config_path="config.json"):
        """Initialize STT Service

        Args:
            config_path: Path to config file
        """
        logger.info("=" * 60)
        logger.info("Initializing STT Service")
        logger.info("=" * 60)

        # Load config
        self.config = self._load_config(config_path)
        logger.info(f"Config loaded: {config_path}")

        # Initialize components
        self.state = "idle"  # idle, recording, processing
        self.hotkey_listener = HotkeyListener()
        self.audio_recorder = AudioRecorder(sample_rate=self.config['sample_rate'])
        self.stt_engine = STTEngine(
            model_size=self.config['model_size'],
            openrouter_api_key=self.config.get('openrouter_api_key', ''),
            openrouter_model=self.config.get('openrouter_model', 'openai/whisper-large-v3')
        )
        self.clipboard_manager = ClipboardManager()
        self.paster = Paster(paste_delay=self.config.get('paste_delay', 0.1))

        logger.info("All components initialized")

    def _load_config(self, config_path):
        """Load configuration from JSON file"""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            logger.info("Using defaults...")
            return {
                "hotkey": "ctrl+shift+a",
                "model_size": "tiny",
                "use_local_stt": True,
                "local_timeout_seconds": 5,
                "openrouter_api_key": "",
                "openrouter_model": "openai/whisper-large-v3",
                "sample_rate": 16000,
                "audio_format": "wav",
                "log_level": "INFO",
                "paste_delay": 0.1,
                "enable_remote_fallback": True
            }

    def on_hotkey_press(self):
        """Handle hotkey press"""
        if self.state == "idle":
            self._start_recording()
        elif self.state == "recording":
            self._stop_recording_and_transcribe()
        elif self.state == "processing":
            logger.warning("Already processing, please wait...")

    def _start_recording(self):
        """Start audio recording"""
        logger.info(">>> RECORDING STARTED <<<")
        self.state = "recording"

        success = self.audio_recorder.start_recording()
        if not success:
            logger.error("Failed to start recording")
            self.state = "idle"

    def _stop_recording_and_transcribe(self):
        """Stop recording and start transcription pipeline"""
        logger.info(">>> RECORDING STOPPED <<<")
        self.state = "processing"

        # Run pipeline in background thread
        Thread(target=self._pipeline, daemon=True).start()

    def _pipeline(self):
        """Execute transcription and paste pipeline"""
        try:
            # Step 1: Stop recording and get audio file
            logger.info("[1/5] Stopping audio capture...")
            audio_path = self.audio_recorder.stop_recording()
            if not audio_path:
                logger.error("Failed to stop recording")
                self.state = "idle"
                return

            # Step 2: Save current clipboard
            logger.info("[2/5] Saving clipboard...")
            self.clipboard_manager.save_clipboard()

            # Step 3: Transcribe audio
            logger.info("[3/5] Transcribing audio...")
            text = self.stt_engine.transcribe(
                audio_path,
                local_timeout=self.config.get('local_timeout_seconds', 5),
                use_local_first=self.config.get('use_local_stt', True)
            )

            if not text:
                logger.error("Transcription failed")
                self.clipboard_manager.restore_clipboard()
                self.state = "idle"
                return

            logger.info(f"Transcription result: {text[:100]}...")

            # Step 4: Set clipboard and paste
            logger.info("[4/5] Setting clipboard and pasting...")
            self.clipboard_manager.set_clipboard(text)
            time.sleep(0.2)  # Brief delay for clipboard to sync
            self.paster.paste_at_cursor()

            # Step 5: Restore clipboard
            logger.info("[5/5] Restoring clipboard...")
            time.sleep(0.2)  # Brief delay before restore
            self.clipboard_manager.restore_clipboard()

            logger.info(">>> PIPELINE COMPLETE <<<")
            self.state = "idle"

        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            import traceback
            traceback.print_exc()
            self.state = "idle"

    def start(self):
        """Start the service"""
        try:
            logger.info("Starting STT Service...")

            # Register hotkey
            hotkey = self.config['hotkey']
            self.hotkey_listener.register(
                hotkey,
                self.on_hotkey_press,
                "Start/Stop recording"
            )

            logger.info(f"Service ready. Press {hotkey} to start recording")
            logger.info("Press Ctrl+C to stop service")

            # Start listening (blocking)
            self.hotkey_listener.start(blocking=True)

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            self.stop()
        except Exception as e:
            logger.error(f"Service error: {e}")
            import traceback
            traceback.print_exc()
            self.stop()

    def stop(self):
        """Stop the service"""
        logger.info("Stopping STT Service...")
        self.hotkey_listener.stop()
        logger.info("Service stopped")


def main():
    """Main entry point"""
    service = STTService()
    service.start()


if __name__ == "__main__":
    main()
