import unittest
from unittest.mock import patch, MagicMock
import os
import setup_assistant

class TestSecurityFix(unittest.TestCase):
    @patch('setup_assistant.platform.system')
    @patch('setup_assistant.subprocess.check_call')
    @patch('setup_assistant.os.path.exists')
    @patch('setup_assistant.os.chdir')
    @patch('setup_assistant.os.makedirs')
    def test_setup_whisper_cpp_windows_shell_false(self, mock_makedirs, mock_chdir, mock_exists, mock_check_call, mock_system):
        # Mock environment
        mock_system.return_value = "Windows"
        mock_exists.return_value = True # whisper.cpp exists

        # Call the function
        setup_assistant.setup_whisper_cpp("cpu")

        # Check if subprocess.check_call was called for the download script
        found_download_call = False
        for call in mock_check_call.call_args_list:
            args, kwargs = call
            # Check for the Windows specific call
            if len(args[0]) >= 3 and "download-ggml-model.cmd" in args[0][2]:
                found_download_call = True
                self.assertNotIn('shell', kwargs, "shell=True should not be used")
                if 'shell' in kwargs:
                    self.assertFalse(kwargs['shell'], "shell should be False")

                # Verify we are using cmd /c
                self.assertEqual(args[0][0], "cmd")
                self.assertEqual(args[0][1], "/c")

        self.assertTrue(found_download_call, "Did not find the download model call")

    @patch('setup_assistant.platform.system')
    @patch('setup_assistant.subprocess.check_call')
    @patch('setup_assistant.os.path.exists')
    @patch('setup_assistant.os.chdir')
    @patch('setup_assistant.os.makedirs')
    def test_setup_whisper_cpp_linux_bash(self, mock_makedirs, mock_chdir, mock_exists, mock_check_call, mock_system):
        # Mock environment
        mock_system.return_value = "Linux"
        mock_exists.return_value = True

        setup_assistant.setup_whisper_cpp("cpu")

        found_download_call = False
        for call in mock_check_call.call_args_list:
            args, kwargs = call
            if len(args[0]) >= 2 and "bash" == args[0][0] and "download-ggml-model.sh" in args[0][1]:
                found_download_call = True
                self.assertNotIn('shell', kwargs)

        self.assertTrue(found_download_call)

if __name__ == '__main__':
    unittest.main()
