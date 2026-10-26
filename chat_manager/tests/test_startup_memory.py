"""Tests for the startup memory buffer.

This is the surface the legacy ``agent_chat_memory`` module used to own.  The
module was removed in this phase: the ChatHistoryManager is now the only
source of a chat memory buffer, and the in-memory buffer is the last resort
rather than a parallel implementation.

Two things are pinned here:

* the buffer is *always* available — the orchestrators call it without
  guarding it, so it must not raise;
* when the primary database is unreachable the manager still comes up
  completely — with a user, sessions and an active session — and the buffer
  is bound to that active session.

The second point is the precondition the removal rests on.  Before the
local fallback existed, an outage raised and the agent lost its history
entirely; the legacy path was the only thing that kept it alive.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from llama_index.core.storage.chat_store.simple_chat_store import SimpleChatStore

import chat_manager.startup as startup
from chat_manager.manager import ChatHistoryManager
from chat_manager.startup import (
    get_in_memory_buffer,
    get_memory_buffer,
    shutdown_chat_manager,
)


#: Nothing listens on that port, so the connection is refused immediately.
UNREACHABLE_URI = "postgresql://postgres:postgres@127.0.0.1:59999/llama_index_db"


class TestStartupMemoryBuffer(unittest.TestCase):
    """The memory buffer is always available, with or without a manager."""

    def setUp(self):
        shutdown_chat_manager()
        self._reset_in_memory_buffer()

    def tearDown(self):
        shutdown_chat_manager()
        self._reset_in_memory_buffer()

    @staticmethod
    def _reset_in_memory_buffer():
        """Drop the cached in-memory buffer so each test starts clean."""
        startup._in_memory_buffer = None
        startup._in_memory_buffer_limit = None

    def test_without_a_manager_the_buffer_is_in_memory(self):
        """No manager means no persistence, but still a working buffer."""
        buffer = get_memory_buffer()

        self.assertIsNotNone(buffer)
        self.assertIsInstance(buffer.chat_store, SimpleChatStore)

    def test_the_in_memory_buffer_is_a_singleton(self):
        """Every caller has to see the same conversation."""
        self.assertIs(get_memory_buffer(), get_memory_buffer())
        self.assertIs(get_in_memory_buffer(), get_memory_buffer())

    def test_the_in_memory_buffer_honours_the_token_limit(self):
        """The limit comes from the environment when one is given."""
        with patch.dict(os.environ, {"TORVALDS_TOKEN_LIMIT": "1234"}):
            buffer = get_in_memory_buffer()

        self.assertEqual(buffer.token_limit, 1234)

    def test_a_broken_token_limit_falls_back_to_the_default(self):
        """A bad value must not take the agent down with it."""
        with patch.dict(os.environ, {"TORVALDS_TOKEN_LIMIT": "not-a-number"}):
            buffer = get_in_memory_buffer()

        self.assertEqual(buffer.token_limit, 5000)

    def test_with_a_manager_the_buffer_is_the_manager_s(self):
        """The manager is the source of truth when it is up."""
        manager = MagicMock()
        manager.is_initialized = True
        manager.get_memory_buffer.return_value = "the-manager-buffer"

        with patch.object(startup, "_chat_manager", manager):
            self.assertEqual(get_memory_buffer(), "the-manager-buffer")

    def test_a_manager_that_cannot_provide_a_buffer_falls_back_to_memory(self):
        """A broken manager must not take the agent's memory with it."""
        manager = MagicMock()
        manager.is_initialized = True
        manager.get_memory_buffer.side_effect = RuntimeError("no active session")

        with patch.object(startup, "_chat_manager", manager):
            buffer = get_memory_buffer()

        self.assertIsInstance(buffer.chat_store, SimpleChatStore)

    def test_an_uninitialised_manager_falls_back_to_memory(self):
        """A manager that exists but is not up yet is not a manager."""
        manager = MagicMock()
        manager.is_initialized = False

        with patch.object(startup, "_chat_manager", manager):
            buffer = get_memory_buffer()

        self.assertIsInstance(buffer.chat_store, SimpleChatStore)
        manager.get_memory_buffer.assert_not_called()


class TestOutagePrecondition(unittest.TestCase):
    """An unreachable primary database must not cost the agent its history."""

    def setUp(self):
        shutdown_chat_manager()
        self._tmpdir = tempfile.TemporaryDirectory()
        self.fallback_path = Path(self._tmpdir.name) / "chat_manager.db"

    def tearDown(self):
        shutdown_chat_manager()
        self._tmpdir.cleanup()

    def test_the_manager_still_comes_up_complete(self):
        """User, sessions and an active session — all of them."""
        manager = ChatHistoryManager(
            storage_uri=UNREACHABLE_URI,
            llama_uri="sqlite:///:memory:",
            fallback_uri=f"sqlite:///{self.fallback_path}",
        )
        try:
            with patch.object(
                ChatHistoryManager, "_get_os_username", return_value="tester"
            ):
                manager.initialize()

                self.assertTrue(manager.is_initialized)
                self.assertTrue(manager.is_degraded)
                self.assertEqual(manager.storage_mode, "fallback")

                self.assertIsNotNone(manager.current_user)
                self.assertEqual(manager.current_user.username, "tester")

                sessions = manager.list_sessions()
                self.assertEqual(len(sessions), 2)

                active = manager.get_active_session()
                self.assertIsNotNone(active)
                self.assertIn(active.session_id, [s.session_id for s in sessions])
        finally:
            manager.shutdown()

    def test_the_buffer_follows_the_active_session(self):
        """The buffer is bound to the session, not to a global key."""
        manager = ChatHistoryManager(
            storage_uri=UNREACHABLE_URI,
            llama_uri="sqlite:///:memory:",
            fallback_uri=f"sqlite:///{self.fallback_path}",
        )
        try:
            with patch.object(
                ChatHistoryManager, "_get_os_username", return_value="tester"
            ):
                manager.initialize()

                buffer = manager.get_memory_buffer()

            self.assertEqual(buffer.chat_store_key, manager.get_active_chat_key())
        finally:
            manager.shutdown()


if __name__ == "__main__":
    unittest.main()
