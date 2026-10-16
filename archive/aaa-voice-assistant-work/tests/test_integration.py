# tests/test_integration.py
import unittest
from unittest.mock import MagicMock, patch
import os
import sys
import numpy as np

# Add path
sys.path.append(os.path.abspath("src"))

# Mock pyaudio before importing modules that rely on it
sys.modules['pyaudio'] = MagicMock()
sys.modules['openwakeword'] = MagicMock()
sys.modules['openwakeword.model'] = MagicMock()
sys.modules['assemblyai'] = MagicMock()

class TestIntegration(unittest.TestCase):

    # Use patch.dict for sys.modules to mock hardware libs AND the audio_recorder module
    # Because assistant_logic does `from .audio_recorder import AudioRecorder` inside try/except
    # or inside methods, we need to make sure `src.audio_recorder` is mockable.

    @patch.dict(sys.modules, {'src.audio_recorder': MagicMock()})
    @patch('src.assistant_logic.WakeWordDetector')
    @patch('src.assistant_logic.WhisperCPPProvider')
    @patch('src.assistant_logic.SystemTTSProvider')
    @patch('src.assistant_logic.LLMService')
    @patch('src.assistant_logic.OverlayWindow')
    @patch('src.assistant_logic.PersonaManager')
    @patch('src.assistant_logic.MemoryStore')
    def test_pipeline(self, MockMemory, MockPersona, MockOverlay, MockLLM, MockTTS, MockSTT, MockWW):

        # Setup Mocks
        stt_instance = MockSTT.return_value
        stt_instance.transcribe.return_value = "Hello world"

        tts_instance = MockTTS.return_value
        llm_instance = MockLLM.return_value
        llm_instance.process.return_value = "Hi there!"

        persona_instance = MockPersona.return_value
        persona_instance.get_persona.return_value = {"name": "TestPersona"}

        memory_instance = MockMemory.return_value
        memory_instance.get_recent_history.return_value = []

        config = {
            "wake_word_enabled": False,
            "stt_provider": "whisper_cpp",
            "tts_provider": "system",
            "llm_backend": "api",
            "silence_threshold": 100,
            "voice_id": "test"
        }

        from src.assistant_logic import Assistant

        assistant = Assistant(config)

        # Manually trigger process logic
        # Mock buffer with fake audio
        assistant.audio_buffer = [np.zeros(16000, dtype=np.int16)]

        # Process
        assistant._process_audio_buffer(mode="assistant")

        # Verify STT called
        stt_instance.transcribe.assert_called()

        # Verify LLM called
        args, _ = llm_instance.process.call_args
        self.assertIn("Hello world", args[0])

        # Verify TTS called
        tts_instance.speak.assert_called_with("Hi there!")

if __name__ == '__main__':
    unittest.main()
