# tests/test_assistant.py
import unittest
from unittest.mock import MagicMock, patch
import json
import os

class TestAssistantConfig(unittest.TestCase):
    def test_default_config(self):
        from src.config_manager import ConfigManager
        cm = ConfigManager("test_config.json")
        self.assertEqual(cm.get("hotkey_ptt"), "ctrl+space")
        if os.path.exists("test_config.json"):
            os.remove("test_config.json")

    def test_merge_config_basic(self):
        from src.config_manager import ConfigManager
        cm = ConfigManager("test_config.json")

        default_cfg = {"a": 1, "b": 2}
        user_cfg = {"b": 3, "c": 4}
        cm._merge_config(default_cfg, user_cfg)

        self.assertEqual(default_cfg, {"a": 1, "b": 3, "c": 4})
        if os.path.exists("test_config.json"):
            os.remove("test_config.json")

    def test_merge_config_recursive(self):
        from src.config_manager import ConfigManager
        cm = ConfigManager("test_config.json")

        default_cfg = {"a": 1, "nested": {"b": 2, "c": 3}}
        user_cfg = {"nested": {"c": 4, "d": 5}}
        cm._merge_config(default_cfg, user_cfg)

        self.assertEqual(default_cfg, {"a": 1, "nested": {"b": 2, "c": 4, "d": 5}})
        if os.path.exists("test_config.json"):
            os.remove("test_config.json")

    def test_merge_config_overwrite_dict_with_value(self):
        from src.config_manager import ConfigManager
        cm = ConfigManager("test_config.json")

        default_cfg = {"a": {"b": 1}}
        user_cfg = {"a": "not_a_dict"}
        cm._merge_config(default_cfg, user_cfg)

        self.assertEqual(default_cfg, {"a": "not_a_dict"})
        if os.path.exists("test_config.json"):
            os.remove("test_config.json")

    def test_merge_config_overwrite_value_with_dict(self):
        from src.config_manager import ConfigManager
        cm = ConfigManager("test_config.json")

        default_cfg = {"a": "string_value"}
        user_cfg = {"a": {"b": 2}}
        cm._merge_config(default_cfg, user_cfg)

        self.assertEqual(default_cfg, {"a": {"b": 2}})
        if os.path.exists("test_config.json"):
            os.remove("test_config.json")

class TestMemoryStore(unittest.TestCase):
    def test_add_and_get(self):
        from src.memory_store import MemoryStore
        ms = MemoryStore("tests/memory.jsonl")
        ms.add_message("user", "Hello", "sess1")
        history = ms.get_recent_history(limit=1, session_id="sess1")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["content"], "Hello")
        if os.path.exists("tests/memory.jsonl"):
            os.remove("tests/memory.jsonl")

    def test_search_memory(self):
        from src.memory_store import MemoryStore
        ms = MemoryStore("tests/memory_search.jsonl")
        ms.add_message("user", "Hello world", "sess1")
        ms.add_message("assistant", "How can I help you today?", "sess1")
        ms.add_message("user", "Tell me a joke", "sess1")

        results = ms.search_memory("hello")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], "Hello world")

        results = ms.search_memory("HELP")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], "How can I help you today?")

        results = ms.search_memory("nonexistent")
        self.assertEqual(len(results), 0)

        if os.path.exists("tests/memory_search.jsonl"):
            os.remove("tests/memory_search.jsonl")

if __name__ == '__main__':
    unittest.main()
