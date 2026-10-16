import unittest
import numpy as np
import os
import wave
from unittest.mock import patch, MagicMock
from src.stt_service import WhisperCPPProvider

class TestSTT(unittest.TestCase):
    @patch('subprocess.run')
    def test_transcribe(self, mock_run):
        mock_result = MagicMock()
        mock_result.stdout = "Hello World"
        mock_run.return_value = mock_result

        provider = WhisperCPPProvider("dummy", "dummy")
        audio = np.zeros(16000, dtype=np.int16)

        # intercept mkstemp to check temp file creation
        import tempfile
        original_mkstemp = tempfile.mkstemp

        temp_paths = []
        def mock_mkstemp(*args, **kwargs):
            fd, path = original_mkstemp(*args, **kwargs)
            temp_paths.append(path)
            return fd, path

        with patch('tempfile.mkstemp', side_effect=mock_mkstemp):
            result = provider.transcribe(audio)

        self.assertEqual(result, "Hello World")
        self.assertTrue(len(temp_paths) == 1)
        # Verify cleanup
        self.assertFalse(os.path.exists(temp_paths[0]))

if __name__ == '__main__':
    unittest.main()
