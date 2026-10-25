"""Tests for the local fallback of the metadata layer.

The metadata layer must not be the reason the agent loses its chat history.
When the primary database cannot be reached, the connector retries against a
local SQLite file and records the degradation — the same shape of degradation
the message backend already has.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chat_manager.manager import ChatHistoryManager
from chat_manager.storage import CustomDBConnector
from chat_manager.storage.connector import (
    DEFAULT_FALLBACK_PATH,
    FALLBACK_DISABLE_ENV,
    FALLBACK_URI_ENV,
    _prepare_sqlite_uri,
)
from chat_manager.user import User


#: A PostgreSQL URI that nothing is listening on.
UNREACHABLE = "postgresql://postgres:postgres@127.0.0.1:59999/llama_index_db"


class TestFallbackUriResolution(unittest.TestCase):
    """Tests for the fallback URI resolution."""

    def setUp(self):
        self._saved = {
            key: os.environ.get(key)
            for key in (FALLBACK_URI_ENV, FALLBACK_DISABLE_ENV)
        }
        for key in (FALLBACK_URI_ENV, FALLBACK_DISABLE_ENV):
            os.environ.pop(key, None)

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_the_default_is_a_local_file(self):
        """Without configuration, the fallback is a local SQLite file."""
        uri = CustomDBConnector._resolve_fallback_uri()
        self.assertTrue(uri.startswith("sqlite:///"))
        self.assertIn(str(DEFAULT_FALLBACK_PATH), uri)

    def test_the_default_path_is_under_the_home_directory(self):
        """The default lives in the user's home directory."""
        self.assertEqual(
            DEFAULT_FALLBACK_PATH.parent, Path.home() / ".torvalds"
        )
        self.assertEqual(DEFAULT_FALLBACK_PATH.name, "chat_manager.db")

    def test_the_fallback_can_be_overridden(self):
        """An explicit URI wins."""
        os.environ[FALLBACK_URI_ENV] = "sqlite:////tmp/explicit_fallback.db"
        uri = CustomDBConnector._resolve_fallback_uri()
        self.assertIn("explicit_fallback.db", uri)

    def test_the_fallback_can_be_switched_off(self):
        """The fallback can be disabled."""
        for value in ("off", "none", "no", "0", "false", "disabled", "OFF"):
            os.environ[FALLBACK_DISABLE_ENV] = value
            self.assertIsNone(
                CustomDBConnector._resolve_fallback_uri(), value
            )

    def test_an_explicit_uri_argument_wins(self):
        """The constructor argument overrides the environment."""
        connector = CustomDBConnector(
            connection_uri="sqlite:///:memory:",
            fallback_uri="sqlite:////tmp/explicit_argument.db",
        )
        self.assertEqual(
            connector._fallback_uri, "sqlite:////tmp/explicit_argument.db"
        )

    def test_an_empty_uri_switches_the_fallback_off(self):
        """An empty fallback URI disables the fallback."""
        connector = CustomDBConnector(
            connection_uri="sqlite:///:memory:", fallback_uri=""
        )
        self.assertEqual(connector._fallback_uri, "")

    def test_none_resolves_the_fallback_from_the_environment(self):
        """None means "resolve from the environment", not "off"."""
        os.environ[FALLBACK_URI_ENV] = "sqlite:////tmp/from_env.db"
        connector = CustomDBConnector(
            connection_uri="sqlite:///:memory:", fallback_uri=None
        )
        self.assertIn("from_env.db", connector._fallback_uri)


class TestPrepareSqliteUri(unittest.TestCase):
    """Tests for the SQLite directory preparation."""

    def test_the_directory_is_created(self):
        """The parent directory of a file-based SQLite URI is created."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "nested" / "deeper" / "chat.db"
            uri = _prepare_sqlite_uri(f"sqlite:///{target}")
            self.assertTrue(target.parent.is_dir())
            self.assertIn(str(target), uri)

    def test_an_absolute_path_is_kept_absolute(self):
        """A four-slash URI keeps its leading slash."""
        uri = _prepare_sqlite_uri("sqlite:////tmp/absolute.db")
        self.assertIn("/tmp/absolute.db", uri)

    def test_memory_is_left_alone(self):
        """An in-memory URI is not treated as a file."""
        self.assertEqual(
            _prepare_sqlite_uri("sqlite:///:memory:"), "sqlite:///:memory:"
        )

    def test_a_postgres_uri_is_left_alone(self):
        """A non-SQLite URI is returned unchanged."""
        uri = "postgresql://user:pass@host:5432/db"
        self.assertEqual(_prepare_sqlite_uri(uri), uri)


class TestConnectorFallback(unittest.TestCase):
    """Tests for the connector's fallback behaviour."""

    def test_a_working_primary_is_not_degraded(self):
        """A working primary database is used as-is."""
        connector = CustomDBConnector(connection_uri="sqlite:///:memory:")
        connector.connect()
        try:
            self.assertTrue(connector.is_connected)
            self.assertFalse(connector.is_degraded)
            self.assertEqual(connector.active_uri, "sqlite:///:memory:")
            self.assertIsNone(connector.degradation_reason)
        finally:
            connector.close()

    def test_an_unreachable_primary_falls_back(self):
        """An unreachable primary database is replaced by the fallback."""
        with tempfile.TemporaryDirectory() as tmp:
            fallback = f"sqlite:///{Path(tmp) / 'chat.db'}"
            connector = CustomDBConnector(
                connection_uri=UNREACHABLE, fallback_uri=fallback
            )
            connector.connect()
            try:
                self.assertTrue(connector.is_connected)
                self.assertTrue(connector.is_degraded)
                self.assertEqual(connector.active_uri, fallback)
                self.assertIn(UNREACHABLE, connector.degradation_reason)
            finally:
                connector.close()

    def test_the_fallback_is_usable(self):
        """The whole user API works on the fallback."""
        with tempfile.TemporaryDirectory() as tmp:
            fallback = f"sqlite:///{Path(tmp) / 'chat.db'}"
            connector = CustomDBConnector(
                connection_uri=UNREACHABLE, fallback_uri=fallback
            )
            connector.connect()
            try:
                created = connector.create_user(
                    User(user_id="fb-1", username="fbuser")
                )
                self.assertEqual(created.username, "fbuser")

                retrieved = connector.get_user_by_username("fbuser")
                self.assertIsNotNone(retrieved)
                self.assertEqual(retrieved.user_id, "fb-1")
            finally:
                connector.close()

    def test_the_fallback_persists_across_connections(self):
        """The fallback is a real database, not a scratch space."""
        with tempfile.TemporaryDirectory() as tmp:
            fallback = f"sqlite:///{Path(tmp) / 'chat.db'}"

            first = CustomDBConnector(
                connection_uri=UNREACHABLE, fallback_uri=fallback
            )
            first.connect()
            try:
                first.create_user(User(user_id="fb-2", username="persisted"))
            finally:
                first.close()

            second = CustomDBConnector(
                connection_uri=UNREACHABLE, fallback_uri=fallback
            )
            second.connect()
            try:
                found = second.get_user_by_username("persisted")
                self.assertIsNotNone(found)
                self.assertEqual(found.user_id, "fb-2")
            finally:
                second.close()

    def test_no_fallback_leaves_the_connector_disconnected(self):
        """With the fallback switched off, the connector stays disconnected."""
        connector = CustomDBConnector(
            connection_uri=UNREACHABLE, fallback_uri=""
        )
        connector.connect()
        try:
            self.assertFalse(connector.is_connected)
            self.assertFalse(connector.is_degraded)
            self.assertIsNone(connector.active_uri)
        finally:
            connector.close()

    def test_close_resets_the_degradation(self):
        """Closing the connector clears the degradation state."""
        with tempfile.TemporaryDirectory() as tmp:
            fallback = f"sqlite:///{Path(tmp) / 'chat.db'}"
            connector = CustomDBConnector(
                connection_uri=UNREACHABLE, fallback_uri=fallback
            )
            connector.connect()
            connector.close()

            self.assertFalse(connector.is_degraded)
            self.assertIsNone(connector.degradation_reason)

    def test_the_operations_refuse_to_run_when_disconnected(self):
        """The guard rail still holds when nothing could be connected."""
        connector = CustomDBConnector(
            connection_uri=UNREACHABLE, fallback_uri=""
        )
        connector.connect()
        with self.assertRaises(RuntimeError):
            connector.get_user_by_username("anyone")


class TestManagerFallback(unittest.TestCase):
    """Tests for the manager's view of the degradation."""

    def test_the_manager_initialises_on_the_fallback(self):
        """The manager comes up completely on the local database."""
        with tempfile.TemporaryDirectory() as tmp:
            fallback = f"sqlite:///{Path(tmp) / 'chat.db'}"
            manager = ChatHistoryManager(
                storage_uri=UNREACHABLE,
                llama_uri="sqlite:///:memory:",
                fallback_uri=fallback,
            )
            with patch.object(
                ChatHistoryManager, "_get_os_username", return_value="fbuser"
            ):
                manager.initialize()

            try:
                self.assertTrue(manager.is_initialized)
                self.assertTrue(manager.is_degraded)
                self.assertEqual(manager.storage_mode, "fallback")
                self.assertEqual(manager.current_user.username, "fbuser")
                self.assertEqual(len(manager.list_sessions()), 2)
                self.assertIsNotNone(manager.get_active_session())
            finally:
                manager.shutdown()

    def test_a_working_primary_is_not_degraded(self):
        """The normal path reports the primary storage."""
        manager = ChatHistoryManager(
            storage_uri="sqlite:///:memory:", llama_uri="sqlite:///:memory:"
        )
        with patch.object(
            ChatHistoryManager, "_get_os_username", return_value="tester"
        ):
            manager.initialize()
        try:
            self.assertFalse(manager.is_degraded)
            self.assertEqual(manager.storage_mode, "primary")
        finally:
            manager.shutdown()

    def test_an_uninitialised_manager_has_no_storage(self):
        """Before initialisation there is no storage mode to report."""
        manager = ChatHistoryManager(
            storage_uri="sqlite:///:memory:", llama_uri="sqlite:///:memory:"
        )
        self.assertFalse(manager.is_degraded)
        self.assertEqual(manager.storage_mode, "unavailable")


class TestChatInfoShowsTheStorageMode(unittest.TestCase):
    """The operator can see where the history lives."""

    def test_the_fallback_is_shown(self):
        """\\chat-info says when the history is local only."""
        from chat_manager.commands import cmd_chat_info
        from chat_manager.session import Session, SessionType

        manager = unittest.mock.MagicMock()
        manager.is_initialized = True
        manager.current_user.username = "tester"
        manager.storage_mode = "fallback"
        manager.get_active_session.return_value = Session(
            session_id="sess-1",
            user_id="user-1",
            session_name="General Chat",
            session_type=SessionType.GENERAL,
            chat_key="key-1",
        )

        result = cmd_chat_info(manager)
        self.assertIn("fallback", result)

    def test_the_primary_is_shown(self):
        """\\chat-info says when the history is shared."""
        from chat_manager.commands import cmd_chat_info
        from chat_manager.session import Session, SessionType

        manager = unittest.mock.MagicMock()
        manager.is_initialized = True
        manager.current_user.username = "tester"
        manager.storage_mode = "primary"
        manager.get_active_session.return_value = Session(
            session_id="sess-1",
            user_id="user-1",
            session_name="General Chat",
            session_type=SessionType.GENERAL,
            chat_key="key-1",
        )

        result = cmd_chat_info(manager)
        self.assertIn("primary", result)


if __name__ == "__main__":
    unittest.main()
