"""Tests for the interactive startup session selector."""

import unittest
from unittest.mock import MagicMock, patch

from chat_manager.manager import ChatHistoryManager
from chat_manager.session import Session, SessionType
from chat_manager.session_selector import (
    format_session_list,
    select_session_interactively,
)


def _make_manager():
    """Create an initialized manager backed by in-memory SQLite."""
    manager = ChatHistoryManager(
        storage_uri="sqlite:///:memory:",
        llama_uri="sqlite:///:memory:",
    )
    with patch.object(ChatHistoryManager, "_get_os_username", return_value="tester"):
        manager.initialize()
    return manager


class TestFormatSessionList(unittest.TestCase):
    """Tests for the session list rendering."""

    def test_empty_list(self):
        """An empty session list is reported."""
        self.assertIn("No sessions", format_session_list([]))

    def test_numbered_entries(self):
        """Sessions are rendered with 1-based numbering."""
        sessions = [
            Session(
                session_id="s1",
                user_id="u1",
                session_name="First",
                session_type=SessionType.GENERAL,
                chat_key="k1",
            ),
            Session(
                session_id="s2",
                user_id="u1",
                session_name="Second",
                session_type=SessionType.CUSTOM,
                chat_key="k2",
            ),
        ]
        output = format_session_list(sessions)
        self.assertIn("1. First", output)
        self.assertIn("2. Second", output)


class TestSelectSessionInteractively(unittest.TestCase):
    """Tests for the interactive selection flow."""

    def setUp(self):
        self.manager = _make_manager()
        self.output = []

    def tearDown(self):
        try:
            self.manager.shutdown()
        except Exception:
            pass

    def _select(self, answers):
        """Run the selector with a scripted list of answers."""
        it = iter(answers)

        def input_func(prompt=""):
            try:
                return next(it)
            except StopIteration:
                return ""

        return select_session_interactively(
            self.manager,
            input_func=input_func,
            output_func=self.output.append,
        )

    def test_select_by_number(self):
        """Picking a number activates that session."""
        sessions = self.manager.list_sessions()
        target = sessions[0]
        selected = self._select([str(sessions.index(target) + 1)])
        self.assertIsNotNone(selected)
        self.assertEqual(selected.session_id, target.session_id)
        self.assertEqual(self.manager.get_active_session().session_id, target.session_id)

    def test_empty_input_keeps_active_session(self):
        """Pressing Enter keeps the currently active session."""
        active = self.manager.get_active_session()
        selected = self._select([""])
        self.assertIsNotNone(selected)
        self.assertEqual(selected.session_id, active.session_id)

    def test_invalid_number_retries(self):
        """An out-of-range number is rejected and the user is asked again."""
        sessions = self.manager.list_sessions()
        selected = self._select(["999", "1"])
        self.assertIsNotNone(selected)
        self.assertTrue(
            any("Please enter a number between" in line for line in self.output)
        )
        self.assertEqual(selected.session_id, sessions[0].session_id)

    def test_non_numeric_input_retries(self):
        """A non-numeric answer is rejected and the user is asked again."""
        selected = self._select(["abc", "1"])
        self.assertIsNotNone(selected)
        self.assertTrue(
            any("is not a valid selection" in line for line in self.output)
        )

    def test_create_new_session(self):
        """'new <name>' creates and activates a custom session."""
        selected = self._select(["new My Chat"])
        self.assertIsNotNone(selected)
        self.assertEqual(selected.session_name, "My Chat")
        self.assertEqual(selected.session_type, SessionType.CUSTOM)

    def test_new_without_name_is_rejected(self):
        """'new' without a name asks for the name again."""
        selected = self._select(["new", "new Real Name"])
        self.assertIsNotNone(selected)
        self.assertEqual(selected.session_name, "Real Name")

    def test_eof_keeps_active_session(self):
        """An EOF on stdin keeps the currently active session."""
        active = self.manager.get_active_session()

        def raising_input(prompt=""):
            raise EOFError

        selected = select_session_interactively(
            self.manager,
            input_func=raising_input,
            output_func=self.output.append,
        )
        self.assertIsNotNone(selected)
        self.assertEqual(selected.session_id, active.session_id)

    def test_uninitialized_manager_returns_none(self):
        """An uninitialized manager yields no selection."""
        selected = select_session_interactively(
            MagicMock(is_initialized=False),
            input_func=lambda prompt="": "",
            output_func=self.output.append,
        )
        self.assertIsNone(selected)


if __name__ == "__main__":
    unittest.main()
