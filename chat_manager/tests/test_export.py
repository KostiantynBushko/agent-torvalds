"""Tests for the ``\\chat-export`` command and the export renderer.

The command prints the content of the active session, or writes it to a
file.  What matters here:

* the content of the session is **verbatim** — the session holds
  arbitrary text, and square brackets in it are not markup;
* the **stored** messages are exported, not only the tail that survives
  the chat-token limit;
* a file is written where the operator asked, and a failure to write it
  is reported instead of raised.

Run with:
    pytest chat_manager/tests/test_export.py -v
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from chat_manager.commands import cmd_chat_export
from chat_manager.commands.handler import handle_chat_command, is_chat_command
from chat_manager.export import (
    render_header,
    render_session,
    render_transcript,
    resolve_path,
    write_export,
)
from chat_manager.session import Session, SessionType
from chat_manager.stats import HistoryStats


def _message(role, content):
    """Return a chat message, the way the agent stores one."""
    from llama_index.core.base.llms.types import ChatMessage, MessageRole

    roles = {
        "user": MessageRole.USER,
        "assistant": MessageRole.ASSISTANT,
        "system": MessageRole.SYSTEM,
    }
    return ChatMessage(role=roles[role], content=content)


def _manager(messages=None, stats=None, initialized=True, active=True):
    """Return a manager that holds *messages*."""
    manager = MagicMock()
    manager.is_initialized = initialized

    session = None
    if active:
        session = Session(
            session_id="sess-1",
            user_id="user-1",
            session_name="General Chat",
            session_type=SessionType.GENERAL,
            chat_key="key-1",
            is_active=True,
        )
    manager.get_active_session.return_value = session
    manager.get_stored_messages.return_value = list(messages or [])

    if stats is None:
        stats = HistoryStats(
            message_count=len(messages or []),
            total_bytes=136,
            stored_tokens=42,
            buffer_tokens=30,
            token_limit=5000,
        )
    manager.get_history_stats.return_value = stats

    return manager


# ---------------------------------------------------------------------------
# The renderer
# ---------------------------------------------------------------------------


class TestRenderTranscript(unittest.TestCase):
    """The transcript reads like the log reads."""

    def test_one_line_per_message(self):
        messages = [
            _message("user", "hello"),
            _message("assistant", "hi"),
        ]
        transcript = render_transcript(messages)

        self.assertEqual(transcript.splitlines(), ["user: hello", "assistant: hi"])

    def test_an_empty_message_says_so(self):
        transcript = render_transcript([_message("assistant", "")])
        self.assertEqual(transcript, "assistant: (empty)")

    def test_an_empty_session_is_an_empty_transcript(self):
        self.assertEqual(render_transcript([]), "")

    def test_the_text_is_verbatim(self):
        """Square brackets in the session are not markup."""
        messages = [_message("user", "a [b] c and a [/nope] tag")]
        transcript = render_transcript(messages)

        self.assertIn("[b] c", transcript)
        self.assertIn("[/nope]", transcript)


class TestRenderHeader(unittest.TestCase):
    """The header says which session the export came from."""

    def setUp(self):
        self.session = Session(
            session_id="sess-1",
            user_id="user-1",
            session_name="General Chat",
            session_type=SessionType.GENERAL,
            chat_key="key-1",
            is_active=True,
        )

    def test_names_the_session(self):
        header = render_header(self.session, 3)
        self.assertIn("General Chat", header)
        self.assertIn("sess-1", header)
        self.assertIn("general", header)

    def test_carries_the_measurements(self):
        stats = HistoryStats(
            message_count=3,
            total_bytes=2048,
            stored_tokens=1234,
            buffer_tokens=900,
            token_limit=8192,
        )
        header = render_header(self.session, 3, stats)

        self.assertIn("3", header)
        self.assertIn("2.0 KB", header)
        self.assertIn("1,234", header)
        self.assertIn("8,192", header)

    def test_without_measurements_the_count_is_still_shown(self):
        header = render_header(self.session, 7)
        self.assertIn("7", header)


class TestRenderSession(unittest.TestCase):
    """The export is the header, a blank line, and the transcript."""

    def setUp(self):
        self.session = Session(
            session_id="sess-1",
            user_id="user-1",
            session_name="General Chat",
            session_type=SessionType.GENERAL,
            chat_key="key-1",
            is_active=True,
        )

    def test_header_and_transcript(self):
        text = render_session(self.session, [_message("user", "hello")])
        lines = text.splitlines()

        self.assertTrue(lines[0].startswith("Session: General Chat"))
        self.assertEqual(lines[-1], "user: hello")

    def test_an_empty_session_says_so(self):
        text = render_session(self.session, [])
        self.assertIn("no messages", text)


# ---------------------------------------------------------------------------
# The file
# ---------------------------------------------------------------------------


class TestResolvePath(unittest.TestCase):
    """The path is the operator's."""

    def test_a_home_path_is_expanded(self):
        resolved = resolve_path("~/session.txt")
        self.assertFalse(str(resolved).startswith("~"))
        self.assertTrue(str(resolved).endswith("session.txt"))

    def test_a_relative_path_stays_relative(self):
        self.assertEqual(str(resolve_path("session.txt")), "session.txt")


class TestWriteExport(unittest.TestCase):
    """The file is written as UTF-8, and it is overwritten."""

    def test_writes_the_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "session.txt"
            written = write_export(target, "hello")

            self.assertEqual(target.read_text(encoding="utf-8"), "hello")
            self.assertEqual(written, 5)

    def test_overwrites_what_was_there(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "session.txt"
            target.write_text("the old export", encoding="utf-8")

            write_export(target, "the new export")
            self.assertEqual(target.read_text(encoding="utf-8"), "the new export")

    def test_keeps_the_characters_of_the_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "session.txt"
            write_export(target, "user: a [b] c")

            self.assertEqual(target.read_text(encoding="utf-8"), "user: a [b] c")

    def test_a_missing_directory_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "missing" / "session.txt"
            with self.assertRaises(OSError):
                write_export(target, "hello")


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------


class TestCmdChatExport(unittest.TestCase):
    """The command prints the session, or writes it to a file."""

    def test_not_initialized(self):
        result = cmd_chat_export(_manager(initialized=False))
        self.assertIn("not initialized", result)

    def test_no_active_session(self):
        result = cmd_chat_export(_manager(active=False))
        self.assertIn("No active session", result)

    def test_prints_the_content_of_the_session(self):
        manager = _manager([_message("user", "hello"), _message("assistant", "hi")])

        result = cmd_chat_export(manager)

        self.assertIn("Session: General Chat", result)
        self.assertIn("user: hello", result)
        self.assertIn("assistant: hi", result)

    def test_the_content_is_verbatim(self):
        manager = _manager([_message("user", "a [b] c and a [/nope] tag")])

        result = cmd_chat_export(manager)

        self.assertIn("[b] c", result)
        self.assertIn("[/nope]", result)

    def test_writes_the_file(self):
        manager = _manager([_message("user", "hello")])

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "session.txt"
            result = cmd_chat_export(manager, path=str(target))

            self.assertIn(str(target), result)
            self.assertIn("1 messages", result)
            self.assertIn("user: hello", target.read_text(encoding="utf-8"))

    def test_a_missing_directory_is_reported_not_raised(self):
        manager = _manager([_message("user", "hello")])

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "missing" / "session.txt"
            result = cmd_chat_export(manager, path=str(target))

        self.assertIn("Could not write", result)
        self.assertIn(str(target), result)

    def test_an_empty_session_is_exported_as_empty(self):
        result = cmd_chat_export(_manager([]))
        self.assertIn("no messages", result)


# ---------------------------------------------------------------------------
# The dispatch
# ---------------------------------------------------------------------------


class TestExportDispatch(unittest.TestCase):
    """The command reaches the operator through the dispatcher."""

    def test_is_a_chat_command(self):
        for cmd in ("\\chat-export", "\\chat-export /tmp/session.txt"):
            self.assertTrue(is_chat_command(cmd), cmd)

    def test_dispatches_to_the_command(self):
        manager = _manager([_message("user", "hello")])

        with patch("chat_manager.startup.get_chat_manager", return_value=manager):
            result = handle_chat_command("\\chat-export")

        self.assertIn("user: hello", result)

    def test_dispatches_with_a_path(self):
        manager = _manager([_message("user", "hello")])

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "session.txt"

            with patch("chat_manager.startup.get_chat_manager", return_value=manager):
                result = handle_chat_command(f"\\chat-export {target}")

            self.assertIn(str(target), result)
            self.assertIn("user: hello", target.read_text(encoding="utf-8"))

    def test_trailing_whitespace_is_the_bare_command(self):
        """The command is stripped, so the trailing spaces are not a path."""
        manager = _manager([_message("user", "hello")])

        with patch("chat_manager.startup.get_chat_manager", return_value=manager):
            result = handle_chat_command("\\chat-export   ")

        self.assertIn("user: hello", result)


# ---------------------------------------------------------------------------
# The real manager
# ---------------------------------------------------------------------------


class TestExportWithARealManager(unittest.TestCase):
    """The export works against the manager the agent really runs."""

    def setUp(self):
        from chat_manager.manager import ChatHistoryManager

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

    def test_the_stored_messages_are_exported(self):
        """The export carries what the session *stores*."""
        self.manager.add_message("hello", "user")
        self.manager.add_message("hi there", "assistant")

        stored = self.manager.get_stored_messages()
        self.assertEqual(len(stored), 2)

        result = cmd_chat_export(self.manager)

        self.assertIn("user: hello", result)
        self.assertIn("assistant: hi there", result)

    def test_the_file_carries_the_same_text(self):
        self.manager.add_message("hello", "user")

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "session.txt"
            cmd_chat_export(self.manager, path=str(target))

            written = target.read_text(encoding="utf-8")
            self.assertIn("user: hello", written)


if __name__ == "__main__":
    unittest.main()
