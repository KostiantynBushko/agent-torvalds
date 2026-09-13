"""
Unit tests for agent_cache_system.

Tests the persistent cache functionality including:
- save_to_cache, load_from_cache, clear_cache
- get_cache_status, context helpers
"""
import unittest
import os
import json
import tempfile
import shutil
from pathlib import Path

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_cache_system import (
    save_to_cache,
    load_from_cache,
    clear_cache,
    get_cache_status,
    update_context_current_dir,
    add_git_repo,
    log_error,
    start_session,
    end_session,
    _get_cache_path,
    _get_default_cache,
)


class TestCacheBasics(unittest.TestCase):
    def setUp(self):
        # Use a temp file for testing
        self.test_cache_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        self.test_cache_file.close()
        os.environ["TORVALDS_CACHE_PATH"] = self.test_cache_file.name
        # Force reload
        import agent_cache_system
        agent_cache_system._cache = None

    def tearDown(self):
        if os.path.exists(self.test_cache_file.name):
            os.unlink(self.test_cache_file.name)
        if "TORVALDS_CACHE_PATH" in os.environ:
            del os.environ["TORVALDS_CACHE_PATH"]
        # Reset module cache
        import agent_cache_system
        agent_cache_system._cache = None

    def test_save_and_load(self):
        result = save_to_cache("test.key", "value")
        self.assertIn("Saved", result)
        loaded = load_from_cache("test.key")
        self.assertEqual(loaded, "value")

    def test_nested_save_and_load(self):
        save_to_cache("a.b.c", 42)
        loaded = load_from_cache("a.b.c")
        self.assertEqual(loaded, 42)

    def test_load_nonexistent_key(self):
        result = load_from_cache("nonexistent.key")
        self.assertIsNone(result)

    def test_clear_cache(self):
        save_to_cache("test.key", "value")
        result = clear_cache()
        self.assertIn("cleared", result.lower())

    def test_get_cache_status(self):
        status = get_cache_status()
        self.assertIn("cache_path", status)
        self.assertIn("file_size_bytes", status)
        self.assertIn("version", status)

    def test_update_context_current_dir(self):
        result = update_context_current_dir("/tmp/test")
        self.assertIn("Saved", result)
        loaded = load_from_cache("context.current_directory")
        self.assertEqual(loaded, "/tmp/test")

    def test_add_git_repo(self):
        result = add_git_repo("/tmp/repo", "main")
        self.assertIn("recorded", result.lower())

    def test_log_error(self):
        result = log_error("Test error message")
        self.assertIn("Error logged", result)

    def test_start_and_end_session(self):
        start_result = start_session()
        self.assertIn("started", start_result.lower())
        end_result = end_session()
        self.assertIn("ended", end_result.lower())


class TestDefaultCache(unittest.TestCase):
    def test_default_structure(self):
        cache = _get_default_cache()
        self.assertIn("version", cache)
        self.assertIn("sessions", cache)
        self.assertIn("context", cache)
        self.assertIn("learnings", cache)
        self.assertIn("state", cache)
        self.assertIn("error_log", cache)


if __name__ == "__main__":
    unittest.main()
