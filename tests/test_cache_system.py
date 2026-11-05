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
    record_frequent_command,
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
        # The cache is written under a lock, and the lock is a file of its
        # own next to the cache.
        lock_file = self.test_cache_file.name + ".lock"
        if os.path.exists(lock_file):
            os.unlink(lock_file)
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


class TestUnserialisableValue(unittest.TestCase):
    """A value JSON cannot hold must not break every later write."""

    def setUp(self):
        # A directory of its own: the test looks at what is left behind,
        # and the temporary folder of the system is shared with the rest
        # of the suite.
        self.test_dir = tempfile.mkdtemp()
        self.cache_path = Path(self.test_dir) / "agent_cache.json"
        os.environ["TORVALDS_CACHE_PATH"] = str(self.cache_path)
        import agent_cache_system
        agent_cache_system._cache = None
        agent_cache_system._load_warnings = []

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
        if "TORVALDS_CACHE_PATH" in os.environ:
            del os.environ["TORVALDS_CACHE_PATH"]
        import agent_cache_system
        agent_cache_system._cache = None

    def test_the_value_is_reported(self):
        result = save_to_cache("context.custom", object())
        self.assertIn("Error saving to cache", result)
        self.assertIn("context.custom", result)

    def test_the_cache_keeps_working(self):
        """The whole point: the later writes must not fail any more."""
        save_to_cache("context.custom", object())
        self.assertIn("Error logged", log_error("boom"))
        self.assertIn("started", start_session().lower())
        self.assertIn("recorded", add_git_repo("/tmp/x", "main").lower())
        self.assertIn("recorded", record_frequent_command("ls").lower())

    def test_the_value_is_not_kept_in_memory(self):
        """A value that cannot be held must not stay in the cache."""
        save_to_cache("context.custom", object())
        self.assertIsNone(load_from_cache("context.custom"))

    def test_the_value_is_not_kept_on_disk(self):
        save_to_cache("context.custom", object())
        with open(self.cache_path) as f:
            self.assertNotIn("custom", json.load(f)["context"])

    def test_no_temp_file_is_left_behind(self):
        """A failed write must not leave a half-written file behind."""
        save_to_cache("context.custom", object())
        leftovers = [n for n in os.listdir(self.test_dir) if n.endswith(".tmp")]
        self.assertEqual(leftovers, [], f"temp files left behind: {leftovers}")


class TestAtomicWrite(unittest.TestCase):
    """The temp file belongs to the writer alone."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.cache_path = Path(self.test_dir) / "agent_cache.json"
        os.environ["TORVALDS_CACHE_PATH"] = str(self.cache_path)
        import agent_cache_system
        agent_cache_system._cache = None

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
        if "TORVALDS_CACHE_PATH" in os.environ:
            del os.environ["TORVALDS_CACHE_PATH"]
        import agent_cache_system
        agent_cache_system._cache = None

    def test_two_writes_use_two_different_temp_files(self):
        """The name of the temp file is not shared between the writers."""
        import agent_cache_system

        seen = []
        real_replace = os.replace

        def recording_replace(src, dst, *args, **kwargs):
            seen.append(str(src))
            return real_replace(src, dst, *args, **kwargs)

        import unittest.mock
        with unittest.mock.patch("os.replace", recording_replace):
            save_to_cache("context.one", 1)
            save_to_cache("context.two", 2)

        self.assertEqual(len(seen), 2)
        self.assertNotEqual(seen[0], seen[1], "the temp file name is shared")
        for name in seen:
            self.assertNotEqual(Path(name).name, "agent_cache.tmp")

    def test_the_cache_file_is_whole(self):
        """What is on the disk is the whole cache, not half of it."""
        save_to_cache("context.current_directory", "/tmp")
        with open(self.cache_path) as f:
            data = json.load(f)
        self.assertEqual(data["context"]["current_directory"], "/tmp")


class TestMergedWrites(unittest.TestCase):
    """Two agents that save at the same time must not erase each other."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.cache_path = Path(self.test_dir) / "agent_cache.json"
        os.environ["TORVALDS_CACHE_PATH"] = str(self.cache_path)
        import agent_cache_system
        agent_cache_system._cache = None

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
        if "TORVALDS_CACHE_PATH" in os.environ:
            del os.environ["TORVALDS_CACHE_PATH"]
        import agent_cache_system
        agent_cache_system._cache = None

    def test_the_entry_of_the_other_agent_survives(self):
        """The lost update of issue #80: B writes, A writes, B is gone."""
        import agent_cache_system

        save_to_cache("context.current_directory", "/tmp")

        copy_a = agent_cache_system._get_cache()              # agent A
        copy_b = json.load(open(self.cache_path))              # agent B

        copy_b["error_log"].append({"message": "B wrote this", "timestamp": "now"})
        agent_cache_system._save_cache(copy_b)

        copy_a["error_log"].append({"message": "A wrote this", "timestamp": "now"})
        agent_cache_system._save_cache(copy_a)

        with open(self.cache_path) as f:
            messages = [e["message"] for e in json.load(f)["error_log"]]
        self.assertIn("B wrote this", messages)
        self.assertIn("A wrote this", messages)

    def test_an_entry_written_twice_is_not_duplicated(self):
        """The same session, written again, is one session."""
        import agent_cache_system

        start_session()
        cache = agent_cache_system._get_cache()
        cache["sessions"][-1]["ended_at"] = "now"
        agent_cache_system._save_cache(cache)

        with open(self.cache_path) as f:
            sessions = json.load(f)["sessions"]
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].get("ended_at"), "now")

    def test_clear_cache_still_clears(self):
        """The merge must not keep what clear_cache is there to remove."""
        log_error("boom")
        self.assertIn("cleared", clear_cache().lower())
        with open(self.cache_path) as f:
            self.assertEqual(json.load(f)["error_log"], [])


class TestDamagedCacheFile(unittest.TestCase):
    """A cache file that cannot be read is reported, not silently replaced."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.cache_path = Path(self.test_dir) / "agent_cache.json"
        os.environ["TORVALDS_CACHE_PATH"] = str(self.cache_path)
        import agent_cache_system
        agent_cache_system._cache = None
        agent_cache_system._load_warnings = []

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
        if "TORVALDS_CACHE_PATH" in os.environ:
            del os.environ["TORVALDS_CACHE_PATH"]
        import agent_cache_system
        agent_cache_system._cache = None

    def test_a_damaged_file_is_reported(self):
        self.cache_path.write_text("{not json at all", encoding="utf-8")
        import agent_cache_system
        agent_cache_system._cache = None

        status = agent_cache_system.get_cache_status()
        self.assertTrue(status["warnings"], "the damaged file was not reported")
        self.assertIn(str(self.cache_path), status["warnings"][0])

    def test_a_damaged_file_is_left_as_it_is(self):
        damaged = "{not json at all"
        self.cache_path.write_text(damaged, encoding="utf-8")
        import agent_cache_system
        agent_cache_system._cache = None
        agent_cache_system.get_cache_status()

        self.assertEqual(self.cache_path.read_text(encoding="utf-8"), damaged)

    def test_the_cache_still_works_afterwards(self):
        self.cache_path.write_text("{not json at all", encoding="utf-8")
        import agent_cache_system
        agent_cache_system._cache = None

        self.assertIn("Saved", save_to_cache("context.current_directory", "/tmp"))
        self.assertEqual(load_from_cache("context.current_directory"), "/tmp")


if __name__ == "__main__":
    unittest.main()
