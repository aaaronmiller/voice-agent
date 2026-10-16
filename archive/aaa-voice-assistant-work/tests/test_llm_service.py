# tests/test_llm_service.py
import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Mock requests before importing llm_service
sys.modules['requests'] = MagicMock()

# Add src to path
sys.path.append(os.path.abspath("src"))

from llm_service import OpenClawBackend

class TestOpenClawBackend(unittest.TestCase):
    def setUp(self):
        self.url = "http://localhost:8000/v1/chat/completions"
        self.backend = OpenClawBackend(self.url)

    @patch('requests.post')
    def test_generate_success(self, mock_post):
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{'message': {'content': 'Hello from OpenClaw'}}]
        }
        mock_post.return_value = mock_response

        prompt = "Hi"
        result = self.backend.generate(prompt)

        # Assertions
        self.assertEqual(result, "Hello from OpenClaw")
        self.assertEqual(len(self.backend.history), 2)
        self.assertEqual(self.backend.history[0], {"role": "user", "content": prompt})
        self.assertEqual(self.backend.history[1], {"role": "assistant", "content": "Hello from OpenClaw"})

        # Check payload
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], self.url)
        self.assertEqual(kwargs['json']['messages'][-1], {"role": "user", "content": prompt})
        self.assertEqual(kwargs['json']['messages'][0]['role'], "system")

    @patch('requests.post')
    def test_generate_custom_system_prompt(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{'message': {'content': 'Aye aye!'}}]
        }
        mock_post.return_value = mock_response

        system_prompt = "You are a pirate."
        self.backend.generate("Hello", system_prompt=system_prompt)

        args, kwargs = mock_post.call_args
        self.assertEqual(kwargs['json']['messages'][0], {"role": "system", "content": system_prompt})

    @patch('requests.post')
    def test_generate_history_windowing(self, mock_post):
        # Fill history with 12 items (6 turns)
        for i in range(12):
            self.backend.history.append({"role": "user" if i % 2 == 0 else "assistant", "content": str(i)})

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{'message': {'content': 'Response'}}]
        }
        mock_post.return_value = mock_response

        self.backend.generate("New Prompt")

        args, kwargs = mock_post.call_args
        messages = kwargs['json']['messages']

        # system prompt + last 10 items + new prompt = 12 messages
        self.assertEqual(len(messages), 12)
        self.assertEqual(messages[0]['role'], "system")
        # messages[1] should be the one with content "2" (the 11th from end including new prompt? No, last 10 from history)
        # History has 12 items. last 10 are indices 2 to 11.
        self.assertEqual(messages[1]['content'], "2")
        self.assertEqual(messages[-1]['content'], "New Prompt")

    @patch('requests.post')
    def test_generate_network_error(self, mock_post):
        mock_post.side_effect = Exception("Connection refused")

        result = self.backend.generate("Hi")
        self.assertIn("Error communicating with OpenClaw: Connection refused", result)

    @patch('requests.post')
    def test_generate_http_error(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("404 Not Found")
        mock_post.return_value = mock_response

        result = self.backend.generate("Hi")
        self.assertIn("Error communicating with OpenClaw: 404 Not Found", result)

if __name__ == '__main__':
    unittest.main()
