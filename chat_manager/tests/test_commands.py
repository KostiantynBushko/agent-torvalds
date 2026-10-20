"""Tests for CLI commands."""

import unittest
from unittest.mock import MagicMock
from chat_manager.commands import (
    cmd_chat_sessions,
    cmd_chat_select,
    cmd_chat_create,
    cmd_chat_delete,
    cmd_chat_rename,
    cmd_chat_info,
    cmd_chat_clear,
)
from chat_manager.session import Session, SessionType
from chat_manager.commands.handler import is_chat_command


class TestCmdChatSessions(unittest.TestCase):
    """Tests for \\chat-sessions command."""

    def test_list_sessions(self):
        """List sessions returns formatted output."""
        manager = MagicMock()
        manager.is_initialized = True
        manager.current_user = MagicMock()
        manager.current_user.username = "testuser"

        session = Session(
            session_id="sess-1",
            user_id="user-1",
            session_name="General Chat",
            session_type=SessionType.GENERAL,
            chat_key="key-1",
            is_active=True,
        )
        manager.list_sessions.return_value = [session]

        result = cmd_chat_sessions(manager)
        self.assertIn("General Chat", result)
        self.assertIn("testuser", result)

    def test_no_sessions(self):
        """No sessions returns appropriate message."""
        manager = MagicMock()
        manager.is_initialized = True
        manager.current_user = MagicMock()
        manager.current_user.username = "testuser"
        manager.list_sessions.return_value = []

        result = cmd_chat_sessions(manager)
        self.assertIn("No sessions", result)

    def test_not_initialized(self):
        """Not initialized returns error."""
        manager = MagicMock()
        manager.is_initialized = False
        result = cmd_chat_sessions(manager)
        self.assertIn("not initialized", result)


class TestCmdChatSelect(unittest.TestCase):
    """Tests for \\chat-select command."""

    def test_select_session(self):
        """Switch to a session."""
        manager = MagicMock()
        manager.is_initialized = True
        session = Session(
            session_id="sess-1",
            user_id="user-1",
            session_name="Project Chat",
            session_type=SessionType.PROJECT,
            chat_key="key-1",
            is_active=True,
        )
        manager.switch_session.return_value = session

        result = cmd_chat_select(manager, "sess-1")
        self.assertIn("Project Chat", result)
        manager.switch_session.assert_called_once_with("sess-1")

    def test_select_nonexistent(self):
        """Select non-existent session."""
        manager = MagicMock()
        manager.is_initialized = True
        manager.switch_session.return_value = None

        result = cmd_chat_select(manager, "nonexistent")
        self.assertIn("not found", result)


class TestCmdChatCreate(unittest.TestCase):
    """Tests for \\chat-create command."""

    def test_create_session(self):
        """Create a new session."""
        manager = MagicMock()
        manager.is_initialized = True
        session = Session(
            session_id="new-sess",
            user_id="user-1",
            session_name="My New Session",
            session_type=SessionType.CUSTOM,
            chat_key="new-key",
        )
        manager.create_session.return_value = session

        result = cmd_chat_create(manager, "My New Session", "custom")
        self.assertIn("My New Session", result)
        self.assertIn("new-sess", result)

    def test_create_invalid_type(self):
        """Create with invalid type."""
        manager = MagicMock()
        manager.is_initialized = True
        result = cmd_chat_create(manager, "Test", "invalid")
        self.assertIn("Invalid session type", result)


class TestCmdChatDelete(unittest.TestCase):
    """Tests for \\chat-delete command."""

    def test_delete_session(self):
        """Delete a session."""
        manager = MagicMock()
        manager.is_initialized = True
        manager.get_active_session.return_value = None
        manager.delete_session.return_value = True

        result = cmd_chat_delete(manager, "sess-to-delete")
        self.assertIn("deleted", result)

    def test_delete_active_session(self):
        """Cannot delete active session."""
        manager = MagicMock()
        manager.is_initialized = True
        active = MagicMock()
        active.session_id = "active-sess"
        manager.get_active_session.return_value = active

        result = cmd_chat_delete(manager, "active-sess")
        self.assertIn("Cannot delete", result)

    def test_delete_nonexistent(self):
        """Delete non-existent session."""
        manager = MagicMock()
        manager.is_initialized = True
        manager.get_active_session.return_value = None
        manager.delete_session.return_value = False

        result = cmd_chat_delete(manager, "nonexistent")
        self.assertIn("not found", result)


if __name__ == "__main__":
    unittest.main()


class TestCmdChatRename(unittest.TestCase):
    """Tests for \\chat-rename command."""

    def test_rename_session(self):
        """Rename a session updates its name."""
        manager = MagicMock()
        manager.is_initialized = True
        session = Session(
            session_id="sess-1",
            user_id="user-1",
            session_name="Renamed",
            session_type=SessionType.CUSTOM,
            chat_key="key-1",
        )
        manager.rename_session.return_value = session

        result = cmd_chat_rename(manager, "sess-1", "Renamed")
        self.assertIn("Renamed", result)
        manager.rename_session.assert_called_once_with("sess-1", "Renamed")

    def test_rename_nonexistent(self):
        """Renaming a missing session reports it."""
        manager = MagicMock()
        manager.is_initialized = True
        manager.rename_session.return_value = None

        result = cmd_chat_rename(manager, "nope", "New")
        self.assertIn("not found", result)

    def test_rename_empty_name(self):
        """An empty name is rejected."""
        manager = MagicMock()
        manager.is_initialized = True

        result = cmd_chat_rename(manager, "sess-1", "   ")
        self.assertIn("cannot be empty", result)

    def test_not_initialized(self):
        """Not initialized returns error."""
        manager = MagicMock()
        manager.is_initialized = False
        result = cmd_chat_rename(manager, "sess-1", "Name")
        self.assertIn("not initialized", result)


class TestCmdChatInfo(unittest.TestCase):
    """Tests for \\chat-info command."""

    def test_shows_active_session(self):
        """Info shows the active session details."""
        manager = MagicMock()
        manager.is_initialized = True
        manager.current_user.username = "testuser"
        session = Session(
            session_id="sess-1",
            user_id="user-1",
            session_name="General Chat",
            session_type=SessionType.GENERAL,
            chat_key="key-1",
        )
        manager.get_active_session.return_value = session

        result = cmd_chat_info(manager)
        self.assertIn("General Chat", result)
        self.assertIn("key-1", result)
        self.assertIn("testuser", result)

    def test_no_active_session(self):
        """Info without an active session is reported."""
        manager = MagicMock()
        manager.is_initialized = True
        manager.get_active_session.return_value = None

        result = cmd_chat_info(manager)
        self.assertIn("No active session", result)

    def test_not_initialized(self):
        """Not initialized returns error."""
        manager = MagicMock()
        manager.is_initialized = False
        result = cmd_chat_info(manager)
        self.assertIn("not initialized", result)


class TestCmdChatClear(unittest.TestCase):
    """Tests for \\chat-clear command."""

    def test_clears_active_session(self):
        """Clear empties the active session."""
        manager = MagicMock()
        manager.is_initialized = True
        session = Session(
            session_id="sess-1",
            user_id="user-1",
            session_name="General Chat",
            session_type=SessionType.GENERAL,
            chat_key="key-1",
        )
        manager.get_active_session.return_value = session

        result = cmd_chat_clear(manager)
        self.assertIn("Cleared", result)
        manager.clear_messages.assert_called_once()

    def test_no_active_session(self):
        """Clear without an active session is reported."""
        manager = MagicMock()
        manager.is_initialized = True
        manager.get_active_session.return_value = None

        result = cmd_chat_clear(manager)
        self.assertIn("No active session", result)

    def test_not_initialized(self):
        """Not initialized returns error."""
        manager = MagicMock()
        manager.is_initialized = False
        result = cmd_chat_clear(manager)
        self.assertIn("not initialized", result)


class TestIsChatCommand(unittest.TestCase):
    """Tests for the is_chat_command detector."""

    def test_detects_chat_commands(self):
        """Chat commands are detected."""
        for cmd in (
            "\\chat-sessions",
            "\\chat-list",
            "\\chat-select abc",
            "\\chat-create name",
            "\\chat-delete id",
            "\\chat-rename id name",
            "\\chat-info",
            "\\chat-clear",
        ):
            self.assertTrue(is_chat_command(cmd), cmd)

    def test_ignores_other_commands(self):
        """Non-chat commands are not detected (and do not raise)."""
        for cmd in ("\\help", "\\exit", "hello world", "", "   "):
            self.assertFalse(is_chat_command(cmd), cmd)
