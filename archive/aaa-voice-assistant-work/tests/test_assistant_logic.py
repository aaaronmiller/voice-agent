# tests/test_assistant_logic.py
import unittest
from unittest.mock import MagicMock, patch
import os
import sys
import numpy as np

# Add src to path
sys.path.append(os.path.abspath("src"))

class TestAssistantLogic(unittest.TestCase):

    # We patch sys.modules to handle lazy imports in Assistant.__init__
    @patch.dict(sys.modules, {'src.audio_recorder': MagicMock()})
    @patch('src.assistant_logic.OverlayWindow')
    @patch('src.assistant_logic.PersonaManager')
    @patch('src.assistant_logic.MemoryStore')
    @patch('src.assistant_logic.LLMService')
    @patch('src.assistant_logic.SystemTTSProvider')
    @patch('src.assistant_logic.WhisperCPPProvider')
    def test_process_audio_assistant_mode(self, MockSTT, MockTTS, MockLLM, MockMemory, MockPersona, MockOverlay):
        from src.assistant_logic import Assistant

        # Configure Mocks
        stt_instance = MockSTT.return_value
        stt_instance.transcribe.return_value = "What time is it?"

        llm_instance = MockLLM.return_value
        llm_instance.process.return_value = "It is noon."

        config = {
            "stt_provider": "whisper_cpp",
            "tts_provider": "system",
            "wake_word_enabled": False
        }

        assistant = Assistant(config)

        # Mock add_message on the instance of MemoryStore
        assistant.memory_store.add_message = MagicMock()

        # Inject audio
        assistant.audio_buffer = [np.zeros(16000, dtype=np.int16)]

        # Run
        assistant._process_audio_buffer(mode="assistant")

        # Assertions
        # Check STT called
        assistant.stt_provider.transcribe.assert_called()

        # Check Memory updated
        # Note: In real logic, add_message is called on self.memory_store
        assistant.memory_store.add_message.assert_any_call("user", "What time is it?")
        assistant.memory_store.add_message.assert_any_call("assistant", "It is noon.")

        # Check TTS called
        assistant.tts_provider.speak.assert_called_with("It is noon.")

    @patch.dict(sys.modules, {'src.audio_recorder': MagicMock()})
    @patch('src.assistant_logic.OverlayWindow')
    @patch('src.assistant_logic.PersonaManager')
    @patch('src.assistant_logic.MemoryStore')
    @patch('src.assistant_logic.LLMService')
    @patch('src.assistant_logic.SystemTTSProvider')
    @patch('src.assistant_logic.WhisperCPPProvider')
    def test_process_audio_type_mode(self, MockSTT, MockTTS, MockLLM, MockMemory, MockPersona, MockOverlay):
        from src.assistant_logic import Assistant

        # Configure Mocks
        stt_instance = MockSTT.return_value
        stt_instance.transcribe.return_value = "Dictated text."

        config = {
            "stt_provider": "whisper_cpp",
            "tts_provider": "system",
            "wake_word_enabled": False
        }

        assistant = Assistant(config)

        # Mock _type_text since it uses keyboard/clipboard
        assistant._type_text = MagicMock()

        # Inject audio
        assistant.audio_buffer = [np.zeros(16000, dtype=np.int16)]

        # Run
        assistant._process_audio_buffer(mode="type")

        # Assertions
        assistant.stt_provider.transcribe.assert_called()

        # Should NOT call LLM or TTS in type mode
        assistant.llm_service.process.assert_not_called()
        assistant.tts_provider.speak.assert_not_called()

        # Should call type_text
        assistant._type_text.assert_called_with("Dictated text.")

if __name__ == '__main__':
    unittest.main()
