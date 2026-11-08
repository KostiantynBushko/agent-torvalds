"""Tests for the ``\\chat-export`` command and the export renderer.

The command prints the content of the active session, or writes it to a
file.  What matters here:

* the content of the session is **verbatim** — the session holds
  arbitrary text, and square brackets in it are not markup;
* the export carries the **stored** messages by default, and the
  **buffered** ones — what the model actually sees — on request;
* the header says which of the two it carries, so a file is never a
  mystery;
* a file is written where the operator asked, and a failure to write it
  is reported instead of raised.

Run with:
    pytest chat_manager/tests/test_export.py -v
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from chat_manager.commands import cmd_chat_export
from chat_manager.commands.handler import handle_chat_command, is_chat_command
from chat_manager.export import (
    FORMAT_JSON,
    FORMAT_TEXT,
    SOURCE_BUFFER,
    SOURCE_STORED,
    message_to_dict,
    render_header,
    render_json,
    render_session,
    render_text,
    render_transcript,
    resolve_path,
    write_export,
)
from chat_manager.session import Session, SessionType


def _message(role, content):
    """Return a chat message, the way the agent stores one."""
    from llama_index.core.base.llms.types import ChatMessage, MessageRole

    roles = {
        "user": MessageRole.USER,
        "assistant": MessageRole.ASSISTANT,
        "system": MessageRole.SYSTEM,
    }
    return ChatMessage(role=roles[role], content=content)


def _rich_message(role, content, thinking=None, tool_calls=None):
    """Return a message that carries blocks, the way the agent stores one."""
    from llama_index.core.base.llms.types import (
        ChatMessage,
        MessageRole,
        TextBlock,
        ThinkingBlock,
        ToolCallBlock,
    )

    roles = {
        "user": MessageRole.USER,
        "assistant": MessageRole.ASSISTANT,
        "system": MessageRole.SYSTEM,
    }

    blocks = [TextBlock(text=content)]
    if thinking:
        blocks.append(ThinkingBlock(content=thinking))
    for name, arguments in tool_calls or []:
        blocks.append(ToolCallBlock(tool_name=name, tool_kwargs=arguments))

    return ChatMessage(role=roles[role], blocks=blocks)


def _session():
    """Return the session the exports are of."""
    return Session(
        session_id="sess-1",
        user_id="user-1",
        session_name="General Chat",
        session_type=SessionType.GENERAL,
        chat_key="key-1",
        is_active=True,
    )


def _manager(messages=None, buffered=None, initialized=True, active=True):
    """Return a manager that holds *messages*.

    The buffer holds the same messages unless *buffered* says otherwise —
    the buffer is the tail of the history, and a session that fits in the
    limit is all of it.
    """
    manager = MagicMock()
    manager.is_initialized = initialized

    manager.get_active_session.return_value = _session() if active else None
    manager.get_stored_messages.return_value = list(messages or [])
    manager.get_messages.return_value = list(
        buffered if buffered is not None else (messages or [])
    )

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
    """The header says which session the export came from, and of what."""

    def test_names_the_session(self):
        header = render_header(_session(), [_message("user", "hello")])
        self.assertIn("General Chat", header)
        self.assertIn("sess-1", header)
        self.assertIn("general", header)

    def test_carries_the_measurements_of_the_exported_messages(self):
        messages = [_message("user", "hello")]
        header = render_header(_session(), messages)

        self.assertIn("Messages: 1", header)
        self.assertIn("5 B", header)
        self.assertIn("Tokens:", header)

    def test_the_stored_source_is_named(self):
        header = render_header(_session(), [], SOURCE_STORED)
        self.assertIn("Source: stored", header)

    def test_the_buffer_source_is_named(self):
        """A file that says nothing of where it came from is a mystery."""
        header = render_header(_session(), [], SOURCE_BUFFER)
        self.assertIn("Source: buffer", header)

    def test_the_measurements_are_of_the_export_not_of_the_session(self):
        """The size and the tokens describe what was exported."""
        messages = [_message("user", "x" * 100)]
        header = render_header(_session(), messages, SOURCE_BUFFER)

        self.assertIn("Messages: 1", header)
        self.assertNotIn("Messages: 5", header)


class TestRenderSession(unittest.TestCase):
    """The export is the header, a blank line, and the transcript."""

    def test_header_and_transcript(self):
        text = render_session(_session(), [_message("user", "hello")])
        lines = text.splitlines()

        self.assertTrue(lines[0].startswith("Session: General Chat"))
        self.assertEqual(lines[-1], "user: hello")

    def test_an_empty_session_says_so(self):
        text = render_session(_session(), [])
        self.assertIn("no messages", text)


# ---------------------------------------------------------------------------
# The JSON
# ---------------------------------------------------------------------------


class TestRenderJson(unittest.TestCase):
    """The JSON export is the same export, in a shape a program reads."""

    def test_it_is_json(self):
        document = json.loads(render_json(_session(), [_message("user", "hello")]))
        self.assertIsInstance(document, dict)

    def test_it_carries_the_session(self):
        document = json.loads(render_json(_session(), []))

        self.assertEqual(document["session"]["id"], "sess-1")
        self.assertEqual(document["session"]["name"], "General Chat")
        self.assertEqual(document["session"]["type"], "general")

    def test_it_carries_the_source(self):
        """A file that does not say what it is, is a mystery file."""
        document = json.loads(render_json(_session(), [], SOURCE_BUFFER))
        self.assertEqual(document["source"], "buffer")

        document = json.loads(render_json(_session(), [], SOURCE_STORED))
        self.assertEqual(document["source"], "stored")

    def test_it_carries_the_measurements(self):
        document = json.loads(render_json(_session(), [_message("user", "hello")]))

        self.assertEqual(document["message_count"], 1)
        self.assertEqual(document["size_bytes"], 5)
        self.assertIn("tokens", document)
        self.assertIn("tokens_estimated", document)

    def test_it_carries_the_messages(self):
        messages = [_message("user", "hello"), _message("assistant", "hi")]
        document = json.loads(render_json(_session(), messages))

        self.assertEqual(len(document["messages"]), 2)
        self.assertEqual(document["messages"][0]["role"], "user")
        self.assertEqual(document["messages"][0]["content"], "hello")
        self.assertEqual(document["messages"][1]["role"], "assistant")
        self.assertEqual(document["messages"][1]["content"], "hi")

    def test_the_content_is_verbatim(self):
        """Square brackets in the session are not markup."""
        messages = [_message("user", "a [b] c and a [/nope] tag")]
        document = json.loads(render_json(_session(), messages))

        self.assertEqual(
            document["messages"][0]["content"], "a [b] c and a [/nope] tag"
        )

    def test_the_characters_of_the_session_survive(self):
        messages = [_message("user", "привіт, 日本語 ✓")]
        document = json.loads(render_json(_session(), messages))

        self.assertEqual(document["messages"][0]["content"], "привіт, 日本語 ✓")

    def test_the_thinking_is_carried(self):
        messages = [_rich_message("assistant", "the answer", thinking="the reasoning")]
        document = json.loads(render_json(_session(), messages))

        self.assertEqual(document["messages"][0]["thinking"], "the reasoning")
        self.assertEqual(document["messages"][0]["content"], "the answer")

    def test_the_tool_calls_are_carried(self):
        messages = [
            _rich_message(
                "assistant",
                "the answer",
                tool_calls=[("pwd", {"path": "/"})],
            )
        ]
        document = json.loads(render_json(_session(), messages))

        calls = document["messages"][0]["tool_calls"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["name"], "pwd")
        self.assertEqual(calls[0]["arguments"], {"path": "/"})

    def test_an_empty_session_is_exported_as_empty(self):
        document = json.loads(render_json(_session(), []))

        self.assertEqual(document["messages"], [])
        self.assertEqual(document["message_count"], 0)

    def test_the_message_helper_stands_alone(self):
        message = _message("user", "hello")
        self.assertEqual(
            message_to_dict(message),
            {
                "role": "user",
                "content": "hello",
                "thinking": None,
                "tool_calls": [],
                "metadata": {},
            },
        )


class TestRenderSessionFormats(unittest.TestCase):
    """The format is chosen, and the text is the default."""

    def test_the_text_is_the_default(self):
        text = render_session(_session(), [_message("user", "hello")])
        self.assertTrue(text.startswith("Session: General Chat"))

    def test_the_text_can_be_asked_for(self):
        text = render_session(
            _session(), [_message("user", "hello")], SOURCE_STORED, FORMAT_TEXT
        )
        self.assertTrue(text.startswith("Session: General Chat"))

    def test_the_json_can_be_asked_for(self):
        text = render_session(
            _session(), [_message("user", "hello")], SOURCE_STORED, FORMAT_JSON
        )
        self.assertEqual(json.loads(text)["messages"][0]["content"], "hello")

    def test_the_text_renderer_is_reachable_on_its_own(self):
        text = render_text(_session(), [_message("user", "hello")])
        self.assertIn("user: hello", text)


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

    def test_the_stored_history_is_exported_by_default(self):
        manager = _manager([_message("user", "the whole session")])

        result = cmd_chat_export(manager)

        self.assertIn("Source: stored", result)
        self.assertIn("the whole session", result)

    def test_the_buffer_can_be_exported(self):
        """The buffer is the tail of the history — what the model sees."""
        manager = _manager(
            messages=[_message("user", "the whole session")],
            buffered=[_message("user", "only the tail")],
        )

        result = cmd_chat_export(manager, source=SOURCE_BUFFER)

        self.assertIn("Source: buffer", result)
        self.assertIn("only the tail", result)
        self.assertNotIn("the whole session", result)

    def test_writes_the_file(self):
        manager = _manager([_message("user", "hello")])

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "session.txt"
            result = cmd_chat_export(manager, path=str(target))

            self.assertIn(str(target), result)
            self.assertIn("1 stored messages", result)
            self.assertIn("user: hello", target.read_text(encoding="utf-8"))

    def test_the_file_says_which_source_it_carries(self):
        manager = _manager([_message("user", "hello")])

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "session.txt"
            cmd_chat_export(manager, path=str(target), source=SOURCE_BUFFER)

            written = target.read_text(encoding="utf-8")
            self.assertIn("Source: buffer", written)

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


class TestCmdChatExportJson(unittest.TestCase):
    """The command writes the JSON when it is asked for."""

    def test_it_prints_json(self):
        manager = _manager([_message("user", "hello")])

        result = cmd_chat_export(manager, output_format=FORMAT_JSON)

        document = json.loads(result)
        self.assertEqual(document["messages"][0]["content"], "hello")
        self.assertEqual(document["source"], "stored")

    def test_the_file_is_json(self):
        manager = _manager([_message("user", "hello")])

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "session.json"
            result = cmd_chat_export(
                manager, path=str(target), output_format=FORMAT_JSON
            )

            self.assertIn("as JSON", result)

            document = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(document["messages"][0]["role"], "user")

    def test_the_buffer_can_be_exported_as_json(self):
        manager = _manager(
            messages=[_message("user", "the whole session")],
            buffered=[_message("user", "only the tail")],
        )

        result = cmd_chat_export(
            manager, source=SOURCE_BUFFER, output_format=FORMAT_JSON
        )

        document = json.loads(result)
        self.assertEqual(document["source"], "buffer")
        self.assertEqual(document["messages"][0]["content"], "only the tail")


# ---------------------------------------------------------------------------
# The dispatch
# ---------------------------------------------------------------------------


class TestExportDispatch(unittest.TestCase):
    """The command reaches the operator through the dispatcher."""

    def test_is_a_chat_command(self):
        for cmd in (
            "\\chat-export",
            "\\chat-export /tmp/session.txt",
            "\\chat-export --buffer",
            "\\chat-export --buffer /tmp/session.txt",
        ):
            self.assertTrue(is_chat_command(cmd), cmd)

    def test_dispatches_to_the_command(self):
        manager = _manager([_message("user", "hello")])

        with patch("chat_manager.startup.get_chat_manager", return_value=manager):
            result = handle_chat_command("\\chat-export")

        self.assertIn("user: hello", result)
        self.assertIn("Source: stored", result)

    def test_dispatches_with_a_path(self):
        manager = _manager([_message("user", "hello")])

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "session.txt"

            with patch("chat_manager.startup.get_chat_manager", return_value=manager):
                result = handle_chat_command(f"\\chat-export {target}")

            self.assertIn(str(target), result)
            self.assertIn("user: hello", target.read_text(encoding="utf-8"))

    def test_the_buffer_option_is_dispatched(self):
        manager = _manager(
            messages=[_message("user", "the whole session")],
            buffered=[_message("user", "only the tail")],
        )

        with patch("chat_manager.startup.get_chat_manager", return_value=manager):
            result = handle_chat_command("\\chat-export --buffer")

        self.assertIn("Source: buffer", result)
        self.assertIn("only the tail", result)

    def test_the_store_option_is_the_default(self):
        manager = _manager([_message("user", "hello")])

        with patch("chat_manager.startup.get_chat_manager", return_value=manager):
            result = handle_chat_command("\\chat-export --store")

        self.assertIn("Source: stored", result)

    def test_the_option_comes_before_the_path(self):
        manager = _manager([_message("user", "hello")])

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "session.txt"

            with patch("chat_manager.startup.get_chat_manager", return_value=manager):
                result = handle_chat_command(f"\\chat-export --buffer {target}")

            # The status names the source, and the file itself carries it.
            self.assertIn("buffered messages", result)

            written = target.read_text(encoding="utf-8")
            self.assertIn("Source: buffer", written)
            self.assertIn("user: hello", written)

    def test_a_path_with_a_space_in_it_survives(self):
        manager = _manager([_message("user", "hello")])

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "my session.txt"

            with patch("chat_manager.startup.get_chat_manager", return_value=manager):
                handle_chat_command(f"\\chat-export {target}")

            self.assertTrue(target.exists())

    def test_the_json_option_is_dispatched(self):
        manager = _manager([_message("user", "hello")])

        with patch("chat_manager.startup.get_chat_manager", return_value=manager):
            result = handle_chat_command("\\chat-export --json")

        document = json.loads(result)
        self.assertEqual(document["messages"][0]["content"], "hello")

    def test_the_json_option_joins_the_source(self):
        """The source and the format are independent."""
        manager = _manager(
            messages=[_message("user", "the whole session")],
            buffered=[_message("user", "only the tail")],
        )

        with patch("chat_manager.startup.get_chat_manager", return_value=manager):
            result = handle_chat_command("\\chat-export --buffer --json")

        document = json.loads(result)
        self.assertEqual(document["source"], "buffer")
        self.assertEqual(document["messages"][0]["content"], "only the tail")

    def test_the_json_option_comes_before_the_path(self):
        manager = _manager([_message("user", "hello")])

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "session.json"

            with patch("chat_manager.startup.get_chat_manager", return_value=manager):
                handle_chat_command(f"\\chat-export --json {target}")

            document = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(document["messages"][0]["content"], "hello")

    def test_the_text_option_is_the_default(self):
        manager = _manager([_message("user", "hello")])

        with patch("chat_manager.startup.get_chat_manager", return_value=manager):
            result = handle_chat_command("\\chat-export --text")

        self.assertTrue(result.startswith("Session: General Chat"))

    def test_two_formats_are_reported(self):
        manager = _manager([_message("user", "hello")])

        with patch("chat_manager.startup.get_chat_manager", return_value=manager):
            result = handle_chat_command("\\chat-export --json --text")

        self.assertIn("Only one format", result)

    def test_the_same_format_twice_is_reported(self):
        manager = _manager([_message("user", "hello")])

        with patch("chat_manager.startup.get_chat_manager", return_value=manager):
            result = handle_chat_command("\\chat-export --json --json")

        self.assertIn("twice", result)

    def test_an_unknown_option_is_reported(self):
        manager = _manager([_message("user", "hello")])

        with patch("chat_manager.startup.get_chat_manager", return_value=manager):
            result = handle_chat_command("\\chat-export --everything")

        self.assertIn("Unknown option", result)
        self.assertIn("Usage:", result)

    def test_two_sources_are_reported(self):
        manager = _manager([_message("user", "hello")])

        with patch("chat_manager.startup.get_chat_manager", return_value=manager):
            result = handle_chat_command("\\chat-export --buffer --store")

        self.assertIn("Only one source", result)

    def test_the_same_option_twice_is_reported(self):
        manager = _manager([_message("user", "hello")])

        with patch("chat_manager.startup.get_chat_manager", return_value=manager):
            result = handle_chat_command("\\chat-export --buffer --buffer")

        self.assertIn("twice", result)

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

        self.assertIn("Source: stored", result)
        self.assertIn("user: hello", result)
        self.assertIn("assistant: hi there", result)

    def test_the_buffer_is_smaller_than_the_store(self):
        """The buffer is the tail of the history — the model sees less."""
        self.manager.update_user_settings(chat_token_limit="256")

        # Two messages of about 200 tokens each: the buffer of 256 keeps
        # one of them, the session keeps both.
        for index in range(2):
            self.manager.add_message(f"{index} " + ("word " * 200), "user")

        stored = self.manager.get_stored_messages()
        buffered = list(self.manager.get_messages())

        self.assertEqual(len(stored), 2)
        self.assertLess(len(buffered), len(stored))

    def test_the_file_carries_the_same_text(self):
        self.manager.add_message("hello", "user")

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "session.txt"
            cmd_chat_export(self.manager, path=str(target))

            written = target.read_text(encoding="utf-8")
            self.assertIn("user: hello", written)


if __name__ == "__main__":
    unittest.main()
