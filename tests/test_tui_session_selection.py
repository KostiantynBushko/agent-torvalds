"""
Tests for the chat session selection of the TUI.

Two defects are covered:

* **D1** - the TUI never proposed the choice of the session at startup.
  The orchestrator skipped the menu when the TUI was up, so the agent
  silently loaded the session that was active last.
* **D2** - inside the TUI a session could only be chosen by typing a
  36-character id.  The sessions are now numbered, and the number is
  what ``\\chat-select`` takes.

The numbering is the numbering of the list of the manager: the startup
menu, ``\\chat-sessions`` and the picker all number the sessions the
same way.

Run with:
    pytest tests/test_tui_session_selection.py -v
"""
import argparse
import asyncio
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chat_manager.commands import cmd_chat_select
from chat_manager.commands.cli import resolve_session_reference
from chat_manager.session import Session, SessionType
from components.tui import chat_history_view

#: The width of the document pane of the TUI at a 120-column terminal.
#: See components/tui/markdown_view.py.
DOCUMENT_PANE_WIDTH = max(40, int(120 * 0.62))


# ---------------------------------------------------------------------------
# Load agent-torvalds-mw.py as a module (its filename is not importable)
# ---------------------------------------------------------------------------

def _load_mw_agent():
    """Load agent-torvalds-mw.py as an importable module."""
    path = ROOT / "agent-torvalds-mw.py"
    spec = importlib.util.spec_from_file_location("agent_torvalds_mw", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["agent_torvalds_mw"] = module
    spec.loader.exec_module(module)
    return module


mw = _load_mw_agent()


def _session(name: str, session_id: str, active: bool = False,
             created: str = "2026-01-01 00:00") -> Session:
    """Build a session for the tests."""
    return Session(
        session_id=session_id,
        user_id="user-1",
        session_name=name,
        session_type=SessionType.CUSTOM,
        chat_key=f"key-{session_id}",
        is_active=active,
        created_at=None,
        updated_at=None,
    )


def _manager(sessions, active=None) -> MagicMock:
    """Build a manager that holds *sessions*.

    Args:
        sessions: The sessions of the user, in the order of the list.
        active: The active session; the first one when None.

    Returns:
        A manager that behaves like the real one for what the commands
        of the chat history use.
    """
    manager = MagicMock()
    manager.is_initialized = True
    manager.list_sessions.return_value = list(sessions)
    manager.get_session.side_effect = lambda sid: next(
        (s for s in sessions if s.session_id == sid), None
    )
    manager.get_active_session.return_value = active or (sessions[0] if sessions else None)
    manager.switch_session.side_effect = lambda sid: next(
        (s for s in sessions if s.session_id == sid), None
    )
    return manager


# ---------------------------------------------------------------------------
# D2 - the sessions are chosen by their number
# ---------------------------------------------------------------------------

class TestSessionNumberReference(unittest.TestCase):
    """A session is named by its number as well as by its id."""

    def _three_sessions(self):
        return [
            _session("First", "sess-1"),
            _session("Second", "sess-2"),
            _session("Third", "sess-3"),
        ]

    def test_the_number_picks_the_session_of_that_position(self):
        sessions = self._three_sessions()
        manager = _manager(sessions)

        result = cmd_chat_select(manager, "2")

        self.assertIn("Second", result)
        manager.switch_session.assert_called_once_with("sess-2")

    def test_the_number_follows_the_order_of_the_list(self):
        """The number is the position in the list of the manager."""
        sessions = self._three_sessions()
        manager = _manager(sessions)

        for index, session in enumerate(sessions, start=1):
            manager.reset_mock()
            cmd_chat_select(manager, str(index))
            manager.switch_session.assert_called_once_with(session.session_id)

    def test_a_number_out_of_the_list_is_refused(self):
        sessions = self._three_sessions()
        manager = _manager(sessions)

        result = cmd_chat_select(manager, "99")

        self.assertIn("There is no session 99", result)
        manager.switch_session.assert_not_called()

    def test_the_id_still_works(self):
        """The id path is untouched: the manager decides."""
        sessions = self._three_sessions()
        manager = _manager(sessions)

        result = cmd_chat_select(manager, "sess-3")

        self.assertIn("Third", result)
        manager.switch_session.assert_called_once_with("sess-3")

    def test_an_unknown_id_is_refused(self):
        manager = _manager(self._three_sessions())
        manager.switch_session.return_value = None

        result = cmd_chat_select(manager, "nope")

        self.assertIn("not found", result)

    def test_an_empty_reference_resolves_to_nothing(self):
        manager = _manager(self._three_sessions())
        self.assertIsNone(resolve_session_reference(manager, ""))
        self.assertIsNone(resolve_session_reference(manager, "   "))


# ---------------------------------------------------------------------------
# D2 - the picker of the TUI
# ---------------------------------------------------------------------------

class TestSessionPicker(unittest.TestCase):
    """The picker lists the sessions and numbers them."""

    def test_the_picker_numbers_the_sessions(self):
        sessions = [
            _session("First", "sess-1"),
            _session("Second", "sess-2"),
        ]
        manager = _manager(sessions)

        md = chat_history_view.render_session_picker_markdown(manager)

        self.assertIn("| 1 |", md)
        self.assertIn("| 2 |", md)
        self.assertIn("First", md)
        self.assertIn("Second", md)

    def test_the_picker_marks_the_active_session(self):
        sessions = [
            _session("First", "sess-1"),
            _session("Second", "sess-2", active=True),
        ]
        manager = _manager(sessions, active=sessions[1])

        md = chat_history_view.render_session_picker_markdown(manager)

        self.assertIn("★ Second", md)
        self.assertNotIn("★ First", md)

    def test_the_picker_says_how_to_select(self):
        manager = _manager([_session("First", "sess-1")])

        md = chat_history_view.render_session_picker_markdown(manager)

        self.assertIn("\\chat-select <number>", md)

    def test_the_picker_without_a_manager(self):
        md = chat_history_view.render_session_picker_markdown(None)
        self.assertIn("not initialized", md)

    def test_the_picker_without_sessions(self):
        manager = _manager([])
        md = chat_history_view.render_session_picker_markdown(manager)
        self.assertIn("No sessions found", md)

    def test_the_picker_carries_no_session_id(self):
        """The picker leaves the id out - that is what makes it usable.

        The list of ``\\chat-sessions`` carries the full id of every
        session.  An id is 36 characters of opaque text, and a row that
        holds one is wider than the document pane: the id is folded in
        the middle and has to be copied by hand.  The picker drops it.
        """
        sessions = [
            _session("First", "0f0a1b2c-3d4e-4f50-8a1b-2c3d4e5f6071"),
            _session("Second", "sess-2", active=True),
        ]
        manager = _manager(sessions, active=sessions[1])

        md = chat_history_view.render_session_picker_markdown(manager)

        self.assertNotIn("0f0a1b2c-3d4e-4f50-8a1b-2c3d4e5f6071", md)

    def test_the_picker_is_narrower_than_the_session_list(self):
        """The picker is the compact view of the same sessions."""
        sessions = [
            _session("agent-torvald-ollama-internal-server-error-500",
                     "0f0a1b2c-3d4e-4f50-8a1b-2c3d4e5f6071"),
            _session("Another session", "sess-2", active=True),
        ]
        manager = _manager(sessions, active=sessions[1])

        picker = chat_history_view.render_session_picker_markdown(manager)
        listing = chat_history_view.render_chat_sessions_markdown(manager)

        picker_rows = [line for line in picker.splitlines() if line.startswith("|")]
        listing_rows = [line for line in listing.splitlines() if line.startswith("|")]

        self.assertTrue(picker_rows, "the picker has no table")
        self.assertTrue(listing_rows, "the list has no table")
        longest_picker = max(len(row) for row in picker_rows)
        longest_listing = max(len(row) for row in listing_rows)
        self.assertLess(
            longest_picker,
            longest_listing,
            "the picker is not narrower than the list it replaces",
        )

    def test_the_picker_row_fits_the_document_pane(self):
        """A row of the picker fits the pane for an ordinary name."""
        sessions = [_session("objective-control-001", "sess-1")]
        manager = _manager(sessions)

        md = chat_history_view.render_session_picker_markdown(manager)

        rows = [line for line in md.splitlines() if line.startswith("|")]
        self.assertTrue(rows, "the picker has no table")
        for row in rows:
            self.assertLessEqual(
                len(row),
                DOCUMENT_PANE_WIDTH,
                f"the row does not fit the document pane: {row!r}",
            )

    def test_the_session_list_carries_the_number_too(self):
        """The numbering of the picker is visible in the list as well."""
        sessions = [_session("First", "sess-1")]
        manager = _manager(sessions)

        md = chat_history_view.render_chat_sessions_markdown(manager)

        self.assertIn("| 1 |", md)
        self.assertIn("sess-1", md)


# ---------------------------------------------------------------------------
# D2 - the command of the TUI
# ---------------------------------------------------------------------------

class TestTuiChatCommand(unittest.TestCase):
    """The TUI answers the chat commands the way it should."""

    def test_a_bare_chat_select_opens_the_picker(self):
        sessions = [_session("First", "sess-1")]
        manager = _manager(sessions)

        with patch("chat_manager.startup.get_chat_manager", return_value=manager):
            md = chat_history_view.handle_chat_command_markdown("\\chat-select")

        self.assertIsNotNone(md)
        self.assertIn("Select a Chat Session", md)
        self.assertIn("First", md)

    def test_chat_select_with_a_number_switches_the_session(self):
        sessions = [
            _session("First", "sess-1"),
            _session("Second", "sess-2"),
        ]
        manager = _manager(sessions)

        with patch("chat_manager.startup.get_chat_manager", return_value=manager):
            md = chat_history_view.handle_chat_command_markdown("\\chat-select 2")

        self.assertIsNotNone(md)
        self.assertIn("Second", md)
        manager.switch_session.assert_called_once_with("sess-2")

    def test_a_command_that_is_not_a_chat_command_is_ignored(self):
        self.assertIsNone(chat_history_view.handle_chat_command_markdown("\\stats"))


# ---------------------------------------------------------------------------
# D2 - the agent works in the session that was picked
# ---------------------------------------------------------------------------

class TestTheAgentFollowsThePickedSession(unittest.TestCase):
    """Switching a session must move the agent with it.

    The memory buffer of the agent is bound to the ``chat_key`` of the
    active session.  A switch that leaves the buffer pointing at the old
    session would show the operator a session he picked and an agent
    that works in the old one.
    """

    def _real_manager(self, sessions):
        """A manager with a real backend and a mocked database.

        The database is mocked so that the test writes nothing: the
        operator's own history is not the place a test belongs.
        """
        from chat_manager.backend import BackendConfig, SimpleChatStoreBackend
        from chat_manager.manager import ChatHistoryManager
        from chat_manager.user import User

        backend = SimpleChatStoreBackend()
        backend.connect(BackendConfig())

        manager = ChatHistoryManager()
        manager._backend = backend
        manager._current_user = User(user_id="user-1", username="tester")
        manager._db = MagicMock()
        manager._db.list_sessions.return_value = list(sessions)
        manager._db.get_session_by_id.side_effect = lambda sid: next(
            (s for s in sessions if s.session_id == sid), None
        )
        manager._db.activate_session.side_effect = lambda sid, uid: next(
            (s for s in sessions if s.session_id == sid), None
        )
        return manager

    def test_the_buffer_follows_the_session_that_was_picked(self):
        first = _session("First", "sess-1", active=True)
        second = _session("Second", "sess-2")
        first.chat_key = "chat-custom-first"
        second.chat_key = "chat-custom-second"

        manager = self._real_manager([first, second])
        manager._active_session = first

        before = manager.get_memory_buffer()
        self.assertEqual(before.chat_store_key, "chat-custom-first")

        cmd_chat_select(manager, "2")

        after = manager.get_memory_buffer()
        self.assertEqual(after.chat_store_key, "chat-custom-second")
        self.assertIsNot(
            before,
            after,
            "the buffer was not rebuilt for the session that was picked",
        )


# ---------------------------------------------------------------------------
# D1 - the TUI proposes the choice at startup
# ---------------------------------------------------------------------------

class TestStartupSessionProposal(unittest.TestCase):
    """The TUI must offer the sessions of the user at startup.

    The menu runs before the layout takes the screen, so the terminal is
    an ordinary console at that point - there is nothing that stops the
    TUI from asking.  The startup tool picker (``--select``) already
    asks the operator the same way, in front of the TUI.
    """

    def _args(self, tui: bool = True) -> argparse.Namespace:
        """The arguments of a run of the orchestrator."""
        return argparse.Namespace(
            write_default_config=False,
            log_file=None,
            log_dir=None,
            log_max_size=1024 * 1024,
            log_max_files=3,
            log_symlink=None,
            log_level="INFO",
            no_stats=True,
            no_events=True,
            verbose_events=False,
            no_hitl=True,
            hitl_method="console",
            hitl_timeout=-1,
            hitl_default_answer="",
            hitl_no_runtime_toggle=True,
            context_guard_on=False,
            no_context_log=True,
            no_chat_history=False,
            no_session_select=False,
            no_prompt_injection=True,
            prompt_template="",
            no_tool_recommendations=True,
            project_path=None,
            auto_scan=False,
            project_type=None,
            select=False,
            full=False,
            top_k=5,
            tui=tui,
            tui_fps=15,
            force_project=None,
        )

    def _run_main(self, args) -> MagicMock:
        """Run ``main()`` with everything heavy mocked.

        Args:
            args: The arguments of the run.

        Returns:
            The mock of ``select_startup_session``, so the caller can see
            whether the menu was offered.
        """
        manager = _manager([_session("First", "sess-1", active=True)])

        app = MagicMock()
        app.run = AsyncMock()

        stdin = MagicMock()
        stdin.isatty.return_value = True

        selector = MagicMock()

        with patch.object(mw, "parse_args", return_value=args), \
                patch.object(mw, "_setup_signal_handlers"), \
                patch.object(mw, "_initialize_prompt_engine"), \
                patch.object(mw, "configure_logging"), \
                patch.object(mw, "resolve_config", return_value=None), \
                patch.object(mw, "initialize_chat_manager", return_value=manager), \
                patch.object(mw, "select_startup_session", selector), \
                patch.object(mw, "get_chat_manager", return_value=manager), \
                patch.object(mw, "build_system_prompt", return_value="prompt"), \
                patch.object(mw, "create_agent", return_value=MagicMock()), \
                patch.object(mw, "get_memory_buffer", return_value=MagicMock()), \
                patch.object(mw, "start_session"), \
                patch.object(mw, "end_session"), \
                patch.object(mw, "_shutdown_chat_manager"), \
                patch.object(mw, "run_classic_repl", new=AsyncMock()), \
                patch.object(mw, "TuiApp", return_value=app), \
                patch.object(mw.config, "ensure_default"), \
                patch.object(sys, "stdin", stdin):
            asyncio.run(mw.main())

        return selector

    def test_the_tui_offers_the_sessions_at_startup(self):
        """The defect: the TUI loaded the last session and said nothing."""
        selector = self._run_main(self._args(tui=True))

        selector.assert_called_once()

    def test_the_menu_is_skipped_when_the_operator_asks_for_it(self):
        args = self._args(tui=True)
        args.no_session_select = True

        selector = self._run_main(args)

        selector.assert_not_called()

    def test_the_classic_console_offers_the_sessions_too(self):
        """The parity: both modes ask."""
        selector = self._run_main(self._args(tui=False))

        selector.assert_called_once()

    def test_the_menu_is_asked_before_the_layout_takes_the_screen(self):
        """The menu runs while the terminal is still an ordinary console.

        The Live display is started at the end of ``main()``.  If the
        menu ran after it, the operator would be typing into the
        alternate screen of the layout.
        """
        args = self._args(tui=True)

        order = []

        app = MagicMock()

        async def _run():
            order.append("layout")

        app.run = _run

        manager = _manager([_session("First", "sess-1", active=True)])
        stdin = MagicMock()
        stdin.isatty.return_value = True

        def _selector(*args, **kwargs):
            order.append("menu")

        with patch.object(mw, "parse_args", return_value=args), \
                patch.object(mw, "_setup_signal_handlers"), \
                patch.object(mw, "_initialize_prompt_engine"), \
                patch.object(mw, "configure_logging"), \
                patch.object(mw, "resolve_config", return_value=None), \
                patch.object(mw, "initialize_chat_manager", return_value=manager), \
                patch.object(mw, "select_startup_session", _selector), \
                patch.object(mw, "get_chat_manager", return_value=manager), \
                patch.object(mw, "build_system_prompt", return_value="prompt"), \
                patch.object(mw, "create_agent", return_value=MagicMock()), \
                patch.object(mw, "get_memory_buffer", return_value=MagicMock()), \
                patch.object(mw, "start_session"), \
                patch.object(mw, "end_session"), \
                patch.object(mw, "_shutdown_chat_manager"), \
                patch.object(mw, "run_classic_repl", new=AsyncMock()), \
                patch.object(mw, "TuiApp", return_value=app), \
                patch.object(mw.config, "ensure_default"), \
                patch.object(sys, "stdin", stdin):
            asyncio.run(mw.main())

        self.assertEqual(order, ["menu", "layout"])


if __name__ == "__main__":
    unittest.main()
