"""Tests for the ChatHistoryManager core orchestrator.

Uses an in-memory SQLite custom DB and the in-memory message backend so the
suite runs without a database server.
"""

import unittest
from unittest.mock import patch

from chat_manager.manager import ChatHistoryManager
from chat_manager.session import Session, SessionType


class TestManagerInitialization(unittest.TestCase):
    """Tests for manager initialization and lifecycle."""

    def setUp(self):
        self.manager = ChatHistoryManager(
            storage_uri="sqlite:///:memory:",
            llama_uri="sqlite:///:memory:",
        )

    def tearDown(self):
        try:
            self.manager.shutdown()
        except Exception:
            pass

    def test_initialize_creates_user_and_sessions(self):
        """Initialize identifies the user and seeds default sessions."""
        with patch.object(ChatHistoryManager, "_get_os_username", return_value="tester"):
            self.manager.initialize()

        self.assertTrue(self.manager.is_initialized)
        self.assertIsNotNone(self.manager.current_user)
        self.assertEqual(self.manager.current_user.username, "tester")

        sessions = self.manager.list_sessions()
        self.assertEqual(len(sessions), 2)
        types = {s.session_type for s in sessions}
        self.assertIn(SessionType.GENERAL, types)
        self.assertIn(SessionType.PROJECT, types)

    def test_initialize_restores_active_session(self):
        """A second initialize restores the previously active session."""
        with patch.object(ChatHistoryManager, "_get_os_username", return_value="tester"):
            self.manager.initialize()
            first = self.manager.get_active_session()
            self.assertIsNotNone(first)

            # Switch away, then re-create the manager and initialize again.
            other = self.manager.list_sessions()
            target = next(s for s in other if s.session_id != first.session_id)
            self.manager.switch_session(target.session_id)

            second = ChatHistoryManager(
                storage_uri="sqlite:///:memory:",
                llama_uri="sqlite:///:memory:",
            )
            # Reuse the same DB handle so state is visible.
            second._db = self.manager._db
            second._current_user = self.manager.current_user
            second._backend = self.manager._backend
            second._ensure_user_sessions()
            self.assertEqual(second.get_active_session().session_id, target.session_id)

    def test_shutdown_is_idempotent(self):
        """Shutdown can be called more than once without raising."""
        with patch.object(ChatHistoryManager, "_get_os_username", return_value="tester"):
            self.manager.initialize()
        self.manager.shutdown()
        self.manager.shutdown()
        self.assertFalse(self.manager.is_initialized)

    def test_get_active_chat_key(self):
        """get_active_chat_key returns the active session's key."""
        with patch.object(ChatHistoryManager, "_get_os_username", return_value="tester"):
            self.manager.initialize()
        session = self.manager.get_active_session()
        self.assertEqual(self.manager.get_active_chat_key(), session.chat_key)


class TestManagerSessionOperations(unittest.TestCase):
    """Tests for session CRUD via the manager."""

    def setUp(self):
        self.manager = ChatHistoryManager(
            storage_uri="sqlite:///:memory:",
            llama_uri="sqlite:///:memory:",
        )
        with patch.object(ChatHistoryManager, "_get_os_username", return_value="tester"):
            self.manager.initialize()

    def tearDown(self):
        try:
            self.manager.shutdown()
        except Exception:
            pass

    def test_create_session(self):
        """create_session returns a persisted session."""
        session = self.manager.create_session("My chat", SessionType.CUSTOM)
        self.assertEqual(session.session_name, "My chat")
        self.assertEqual(session.session_type, SessionType.CUSTOM)
        self.assertTrue(session.chat_key)

        ids = [s.session_id for s in self.manager.list_sessions()]
        self.assertIn(session.session_id, ids)

    def test_switch_session_updates_active(self):
        """switch_session activates the target and invalidates the buffer."""
        new_session = self.manager.create_session("Other", SessionType.CUSTOM)
        result = self.manager.switch_session(new_session.session_id)
        self.assertIsNotNone(result)
        self.assertEqual(self.manager.get_active_session().session_id, new_session.session_id)

    def test_switch_to_unknown_session_returns_none(self):
        """Switching to an unknown session returns None."""
        self.assertIsNone(self.manager.switch_session("does-not-exist"))

    def test_delete_session(self):
        """delete_session removes a non-active session."""
        session = self.manager.create_session("Temp", SessionType.CUSTOM)
        self.assertTrue(self.manager.delete_session(session.session_id))
        ids = [s.session_id for s in self.manager.list_sessions()]
        self.assertNotIn(session.session_id, ids)

    def test_delete_active_session_refused(self):
        """The active session cannot be deleted."""
        active = self.manager.get_active_session()
        self.assertFalse(self.manager.delete_session(active.session_id))

    def test_rename_session(self):
        """rename_session updates the session name."""
        session = self.manager.create_session("Old name", SessionType.CUSTOM)
        renamed = self.manager.rename_session(session.session_id, "New name")
        self.assertIsNotNone(renamed)
        self.assertEqual(renamed.session_name, "New name")

    def test_rename_session_rejects_empty_name(self):
        """Renaming to an empty name raises ValueError."""
        session = self.manager.create_session("Keep", SessionType.CUSTOM)
        with self.assertRaises(ValueError):
            self.manager.rename_session(session.session_id, "   ")

    def test_get_session_returns_owned_session(self):
        """get_session returns the current user's session."""
        session = self.manager.create_session("Owned", SessionType.CUSTOM)
        found = self.manager.get_session(session.session_id)
        self.assertIsNotNone(found)
        self.assertEqual(found.session_id, session.session_id)

    def test_get_session_rejects_other_users_session(self):
        """get_session returns None for a session owned by another user."""
        other = Session(
            session_id="someone-elses",
            user_id="different-user",
            session_name="Private",
            session_type=SessionType.CUSTOM,
            chat_key="other-key",
        )
        self.manager._db.create_session(other)
        self.assertIsNone(self.manager.get_session("someone-elses"))

    def test_update_session(self):
        """update_session persists changed fields."""
        session = self.manager.create_session("Before", SessionType.CUSTOM)
        updated = self.manager.update_session(session.session_id, session_name="After")
        self.assertIsNotNone(updated)
        self.assertEqual(updated.session_name, "After")

    def test_switch_to_other_users_session_refused(self):
        """A user cannot activate another user's session."""
        other = Session(
            session_id="not-mine",
            user_id="another-user",
            session_name="Theirs",
            session_type=SessionType.CUSTOM,
            chat_key="their-key",
        )
        self.manager._db.create_session(other)
        self.assertIsNone(self.manager.switch_session("not-mine"))


class TestManagerMessages(unittest.TestCase):
    """Tests for message routing and session isolation."""

    def setUp(self):
        self.manager = ChatHistoryManager(
            storage_uri="sqlite:///:memory:",
            llama_uri="sqlite:///:memory:",
        )
        with patch.object(ChatHistoryManager, "_get_os_username", return_value="tester"):
            self.manager.initialize()

    def tearDown(self):
        try:
            self.manager.shutdown()
        except Exception:
            pass

    def test_memory_buffer_uses_session_chat_key(self):
        """The buffer is bound to the active session's chat key."""
        session = self.manager.get_active_session()
        buffer = self.manager.get_memory_buffer()
        self.assertEqual(buffer.chat_store_key, session.chat_key)

    def test_add_message_accepts_content_and_role(self):
        """add_message builds a ChatMessage and stores it."""
        self.manager.add_message("hello there", "user")
        messages = self.manager.get_messages()
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].content, "hello there")

    def test_add_message_rejects_invalid_role(self):
        """An invalid role raises ValueError."""
        with self.assertRaises(ValueError):
            self.manager.add_message("hello", "not-a-role")

    def test_sessions_are_isolated(self):
        """Messages do not leak between sessions."""
        session_a = self.manager.get_active_session()
        self.manager.add_message("message for A", "user")
        self.assertEqual(len(self.manager.get_messages()), 1)

        session_b = self.manager.create_session("B", SessionType.CUSTOM)
        self.manager.switch_session(session_b.session_id)

        # Session B starts empty.
        self.assertEqual(len(self.manager.get_messages()), 0)

        self.manager.add_message("message for B", "user")
        self.assertEqual(len(self.manager.get_messages()), 1)

        # Switching back to A restores only A's message.
        self.manager.switch_session(session_a.session_id)
        messages = self.manager.get_messages()
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].content, "message for A")

    def test_clear_messages_empties_active_session(self):
        """clear_messages removes the history of the active session."""
        self.manager.add_message("to be cleared", "user")
        self.assertEqual(len(self.manager.get_messages()), 1)

        self.manager.clear_messages()
        self.assertEqual(len(self.manager.get_messages()), 0)

    def test_clear_messages_keeps_other_sessions(self):
        """Clearing one session does not affect another."""
        session_a = self.manager.get_active_session()
        self.manager.add_message("A message", "user")

        session_b = self.manager.create_session("B", SessionType.CUSTOM)
        self.manager.switch_session(session_b.session_id)
        self.manager.add_message("B message", "user")

        self.manager.clear_messages()
        self.assertEqual(len(self.manager.get_messages()), 0)

        self.manager.switch_session(session_a.session_id)
        self.assertEqual(len(self.manager.get_messages()), 1)


class TestPlanMandatedApi(unittest.TestCase):
    """Tests for the Step 7 API surface mandated by the implementation plan.

    The plan lists ``identify_user``, ``select_session``, ``put_message`` and
    ``close`` by name. These tests pin the public contract so future
    refactors cannot silently drop them.
    """

    def setUp(self):
        self.manager = ChatHistoryManager(
            storage_uri="sqlite:///:memory:",
            llama_uri="sqlite:///:memory:",
        )
        with patch.object(ChatHistoryManager, "_get_os_username", return_value="tester"):
            self.manager.initialize()

    def tearDown(self):
        try:
            self.manager.close()
        except Exception:
            pass

    def test_identify_user_returns_current_user(self):
        """identify_user() returns the provisioned OS user."""
        user = self.manager.identify_user()
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "tester")
        self.assertIs(user, self.manager.current_user)

    def test_select_session_activates_session(self):
        """select_session() activates the target session like switch_session()."""
        target = self.manager.create_session("Selected", SessionType.CUSTOM)
        activated = self.manager.select_session(target.session_id)

        self.assertIsNotNone(activated)
        self.assertEqual(activated.session_id, target.session_id)
        self.assertEqual(self.manager.get_active_session().session_id, target.session_id)

    def test_select_session_rejects_foreign_session(self):
        """select_session() returns None for an unknown session."""
        self.assertIsNone(self.manager.select_session("00000000-0000-0000-0000-000000000000"))

    def test_put_message_adds_to_active_session(self):
        """put_message() appends a message to the active session."""
        self.manager.put_message("hello via put_message", "user")
        messages = self.manager.get_messages()
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].content, "hello via put_message")

    def test_close_is_idempotent(self):
        """close() can be called more than once without raising."""
        self.manager.close()
        self.manager.close()
        self.assertFalse(self.manager.is_initialized)

    def test_create_session_accepts_metadata(self):
        """create_session() persists the optional metadata argument."""
        session = self.manager.create_session(
            "With meta",
            SessionType.CUSTOM,
            metadata={"tag": "important", "n": 7},
        )
        fetched = self.manager.get_session(session.session_id)
        self.assertEqual(fetched.metadata.get("tag"), "important")
        self.assertEqual(fetched.metadata.get("n"), 7)

    def test_create_session_defaults_to_empty_metadata(self):
        """create_session() without metadata yields an empty dict."""
        session = self.manager.create_session("No meta", SessionType.CUSTOM)
        fetched = self.manager.get_session(session.session_id)
        self.assertEqual(fetched.metadata, {})


if __name__ == "__main__":
    unittest.main()
