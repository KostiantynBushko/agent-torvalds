"""
Unit tests for the Multi-Window Agent feature parity work.

Covers the three features the multi-window agent was missing relative to
the classic orchestrator (agent-torvalds.py):
  - Startup tool selection (--select / \\tools)
  - Project manager (--project-path, --auto-scan, \\projects, ...)
  - Chat history manager (--no-chat-history, \\chat-sessions, ...)

Run with:
    pytest tests/test_multi_window_parity.py -v
"""
import argparse
import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure the repository root is on the path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


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


# ---------------------------------------------------------------------------
# CLI parity tests
# ---------------------------------------------------------------------------

class TestMultiWindowCLIParity(unittest.TestCase):
    """The MW agent must expose the same startup flags as agent-torvalds.py."""

    def _parse(self, argv):
        """Parse arguments with the MW agent's parser."""
        with patch.object(sys, "argv", ["agent-torvalds-mw.py"] + argv):
            return mw.parse_args()

    def test_select_flag_exists(self):
        args = self._parse(["--select"])
        self.assertTrue(args.select)
        self.assertFalse(args.full)

    def test_full_and_select_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit):
            self._parse(["--full", "--select"])

    def test_project_path_flag(self):
        args = self._parse(["--project-path", "/tmp/example"])
        self.assertEqual(args.project_path, "/tmp/example")

    def test_auto_scan_and_project_type(self):
        args = self._parse(["--auto-scan", "--project-type", "Python"])
        self.assertTrue(args.auto_scan)
        self.assertEqual(args.project_type, "Python")

    def test_prompt_injection_flags(self):
        args = self._parse([
            "--no-prompt-injection",
            "--prompt-template", "/tmp/tpl.txt",
            "--no-tool-recommendations",
            "--force-project", "myproj",
        ])
        self.assertTrue(args.no_prompt_injection)
        self.assertEqual(args.prompt_template, "/tmp/tpl.txt")
        self.assertTrue(args.no_tool_recommendations)
        self.assertEqual(args.force_project, "myproj")

    def test_chat_history_flags(self):
        args = self._parse(["--no-chat-history", "--no-session-select"])
        self.assertTrue(args.no_chat_history)
        self.assertTrue(args.no_session_select)

    def test_tui_flags_still_present(self):
        args = self._parse([])
        self.assertTrue(args.tui)
        args = self._parse(["--no-tui"])
        self.assertFalse(args.tui)

    def test_defaults_match_classic_agent(self):
        """Core defaults must not drift between the two orchestrators."""
        args = self._parse([])
        self.assertEqual(args.top_k, mw.SIMILARITY_TOP_K)
        self.assertEqual(args.log_level, "INFO")
        self.assertFalse(args.no_stats)
        self.assertFalse(args.no_events)
        self.assertFalse(args.verbose_events)
        self.assertFalse(args.no_hitl)
        self.assertIn(args.hitl_method, ("console", "whiptail"))
        self.assertEqual(args.hitl_timeout, mw.HITL_TIMEOUT)

    def test_the_file_logging_flags(self):
        """Both orchestrators must expose the same file-logging flags."""
        args = self._parse(
            [
                "--log-file", "agent.log",
                "--log-dir", "/tmp/logs",
                "--log-max-size", "20MB",
                "--log-max-files", "3",
                "--log-symlink", "current.log",
            ]
        )
        self.assertEqual(args.log_file, "agent.log")
        self.assertEqual(args.log_dir, "/tmp/logs")
        self.assertEqual(args.log_max_size, 20 * 1024 * 1024)
        self.assertEqual(args.log_max_files, 3)
        self.assertEqual(args.log_symlink, "current.log")

    def test_the_file_logging_is_off_by_default(self):
        args = self._parse([])
        self.assertIsNone(args.log_file)
        self.assertIsNone(args.log_dir)
        self.assertIsNone(args.log_symlink)

    def test_the_file_logging_flags_match_the_classic_agent(self):
        """The flag surface must not drift between the two orchestrators."""
        classic_path = ROOT / "agent-torvalds.py"
        spec = importlib.util.spec_from_file_location(
            "agent_torvalds_classic_logging", classic_path
        )
        classic = importlib.util.module_from_spec(spec)
        sys.modules["agent_torvalds_classic_logging"] = classic
        spec.loader.exec_module(classic)

        with patch.object(sys, "argv", ["agent-torvalds.py"]):
            classic_args = classic.parse_args()
        mw_args = self._parse([])

        for name in ("log_file", "log_dir", "log_max_size", "log_max_files",
                     "log_symlink"):
            self.assertEqual(
                getattr(classic_args, name),
                getattr(mw_args, name),
                f"the {name} default drifted between the two orchestrators",
            )


# ---------------------------------------------------------------------------
# Tool collection parity
# ---------------------------------------------------------------------------

class TestToolCollectionParity(unittest.TestCase):
    """_collect_all_tools must expose every toolkit, including project tools."""

    def test_collect_all_tools_includes_project_manager_tools(self):
        tools = mw._collect_all_tools()
        names = {t.metadata.name for t in tools}
        self.assertIn("load_project", names)
        self.assertIn("scan_directory", names)
        self.assertIn("check_git_status", names)

    def test_collect_all_tools_includes_core_toolkits(self):
        tools = mw._collect_all_tools()
        names = {t.metadata.name for t in tools}
        # A representative tool from several toolkits
        for expected in ("execute_shell_command", "git_get_status"):
            self.assertIn(expected, names, f"{expected} missing from tool collection")

    def test_collect_all_tools_is_non_empty(self):
        self.assertGreater(len(mw._collect_all_tools()), 50)

    def test_collect_all_tools_matches_classic_agent(self):
        """The MW agent must expose exactly the same tools as agent-torvalds.py."""
        classic_path = ROOT / "agent-torvalds.py"
        spec = importlib.util.spec_from_file_location("agent_torvalds_classic", classic_path)
        classic = importlib.util.module_from_spec(spec)
        sys.modules["agent_torvalds_classic"] = classic
        spec.loader.exec_module(classic)

        mw_names = {t.metadata.name for t in mw._collect_all_tools()}
        classic_names = {t.metadata.name for t in classic._collect_all_tools()}

        self.assertEqual(
            mw_names - classic_names,
            set(),
            "MW agent exposes tools the classic agent does not",
        )
        self.assertEqual(
            classic_names - mw_names,
            set(),
            "MW agent is missing tools the classic agent exposes",
        )


# ---------------------------------------------------------------------------
# Tool selection view
# ---------------------------------------------------------------------------

class TestToolSelectionView(unittest.TestCase):
    """Tests for components.tui.tool_selection_view."""

    def setUp(self):
        from components.tui import tool_selection_view

        self.view = tool_selection_view

    def test_is_tool_selection_command(self):
        self.assertTrue(self.view.is_tool_selection_command("\\tools"))
        self.assertTrue(self.view.is_tool_selection_command("\\tool-list"))
        self.assertTrue(self.view.is_tool_selection_command("\\tool-select 1-3"))
        self.assertTrue(self.view.is_tool_selection_command("\\TOOLS"))
        self.assertFalse(self.view.is_tool_selection_command("\\stats"))
        self.assertFalse(self.view.is_tool_selection_command(""))
        self.assertFalse(self.view.is_tool_selection_command(None))

    def test_render_categories_markdown_contains_table(self):
        from llama_index.core.tools import FunctionTool

        def _make(name, desc):
            def _fn():
                """noop"""
                return "ok"

            return FunctionTool.from_defaults(
                fn=_fn,
                name=name,
                description=desc,
            )

        tools = [
            _make("add_two", "Add two numbers. Category: Mathematics"),
            _make("git_status", "Get the repository status. Category: Version Control"),
        ]
        groups = {
            "Mathematics": [tools[0]],
            "Version Control": [tools[1]],
        }
        md = self.view.render_categories_markdown(groups, 2)
        self.assertIn("| # | Category | Tools | Capabilities |", md)
        self.assertIn("Mathematics", md)
        self.assertIn("Version Control", md)
        self.assertIn("2 tools across 2 categories", md)

    def test_render_tool_list_markdown(self):
        tool = MagicMock()
        tool.metadata.name = "demo_tool"
        tool.metadata.description = "Does a thing. Category: Demo"
        md = self.view.render_tool_list_markdown([tool])
        self.assertIn("demo_tool", md)
        self.assertIn("Does a thing", md)

    def test_select_tools_interactive_tui_with_selection(self):
        from agent_tool_selection import group_tools_by_category
        from components.tui.tool_selection_view import discover_all_tools

        tools = discover_all_tools()
        groups = group_tools_by_category(tools)
        categories = list(groups.keys())

        captured = []

        def fake_input(prompt=""):
            captured.append(prompt)
            return "1"

        selected = self.view.select_tools_interactive_tui(
            all_tools=tools,
            input_func=fake_input,
            output_func=lambda text: None,
        )

        self.assertEqual(len(captured), 1)
        self.assertGreater(len(selected), 0)

        # The selected tools must all belong to the first category
        expected_count = len(groups[categories[0]])
        self.assertEqual(len(selected), expected_count)

    def test_select_tools_interactive_tui_with_range(self):
        from components.tui.tool_selection_view import discover_all_tools

        tools = discover_all_tools()
        selected = self.view.select_tools_interactive_tui(
            all_tools=tools,
            input_func=lambda prompt="": "1-2",
            output_func=lambda text: None,
        )
        self.assertGreater(len(selected), 0)

    def test_select_tools_interactive_tui_retries_on_invalid(self):
        answers = iter(["not-a-number", "999999", "1"])
        prompts = []

        def fake_input(prompt=""):
            prompts.append(prompt)
            return next(answers)

        selected = self.view.select_tools_interactive_tui(
            input_func=fake_input,
            output_func=lambda text: None,
        )
        self.assertEqual(len(prompts), 3)
        self.assertGreater(len(selected), 0)

    def test_select_tools_interactive_tui_handles_eof(self):
        def raise_eof(prompt=""):
            raise EOFError

        selected = self.view.select_tools_interactive_tui(
            input_func=raise_eof,
            output_func=lambda text: None,
        )
        self.assertEqual(selected, [])


# ---------------------------------------------------------------------------
# Project manager view
# ---------------------------------------------------------------------------

class TestProjectManagerView(unittest.TestCase):
    """Tests for components.tui.project_manager_view."""

    def setUp(self):
        from components.tui import project_manager_view

        self.view = project_manager_view

    def test_is_project_command(self):
        self.assertTrue(self.view.is_project_command("\\projects"))
        self.assertTrue(self.view.is_project_command("\\project-list"))
        self.assertTrue(self.view.is_project_command("\\project-info myproj"))
        self.assertTrue(self.view.is_project_command("\\project-status"))
        self.assertTrue(self.view.is_project_command("\\project-summary"))
        self.assertFalse(self.view.is_project_command("\\stats"))
        self.assertFalse(self.view.is_project_command(""))
        self.assertFalse(self.view.is_project_command(None))

    def test_has_error_distinguishes_null_error(self):
        """A payload with error=None must not be treated as a failure."""
        self.assertFalse(self.view._has_error({"error": None}))
        self.assertFalse(self.view._has_error({}))
        self.assertTrue(self.view._has_error({"error": "boom"}))

    def test_render_projects_markdown_with_projects(self):
        payload = (
            '{"workspace_path": "/ws", "count": 1, "projects": '
            '[{"name": "demo", "type": "Python", "confidence": 0.9, '
            '"git_repo": true, "has_actions": false}]}'
        )
        with patch(
            "project_manager.agent_project_manager_toolkit.list_projects",
            return_value=payload,
        ):
            md = self.view.render_projects_markdown()

        self.assertIn("demo", md)
        self.assertIn("Python", md)
        self.assertIn("/ws", md)

    def test_render_projects_markdown_empty(self):
        payload = '{"workspace_path": "/ws", "count": 0, "projects": []}'
        with patch(
            "project_manager.agent_project_manager_toolkit.list_projects",
            return_value=payload,
        ):
            md = self.view.render_projects_markdown()

        self.assertIn("No projects registered yet", md)

    def test_render_projects_markdown_reports_error(self):
        with patch(
            "project_manager.agent_project_manager_toolkit.list_projects",
            return_value='{"error": "no workspace"}',
        ):
            md = self.view.render_projects_markdown()

        self.assertIn("no workspace", md)

    def test_render_project_info_markdown(self):
        payload = (
            '{"name": "demo", "type": "Python", "confidence": 0.85, '
            '"path": "/ws/demo", "git_repo": true, "git_branch": "main", '
            '"metadata": {"description": "A demo", "framework": "FastAPI"}}'
        )
        with patch(
            "project_manager.agent_project_manager_toolkit.get_project_details",
            return_value=payload,
        ):
            md = self.view.render_project_info_markdown("demo")

        self.assertIn("demo", md)
        self.assertIn("FastAPI", md)
        self.assertIn("main", md)

    def test_render_project_status_markdown(self):
        payload = (
            '{"path": "/ws", "is_git_repo": true, "branch": "main", '
            '"commit_hash": "abc123", "has_uncommitted": true, '
            '"has_staged": false, "has_untracked": false, "has_modified": true, '
            '"uncommitted_count": 1, "files": ['
            '{"path": "a.py", "status": " M", "staged": false, "modified": true, '
            '"untracked": false, "deleted": false, "renamed": false}], '
            '"error": null}'
        )
        with patch(
            "project_manager.agent_project_manager_toolkit.check_git_status",
            return_value=payload,
        ):
            md = self.view.render_project_status_markdown()

        self.assertIn("main", md)
        self.assertIn("abc123", md)
        self.assertIn("a.py", md)
        self.assertNotIn("**Error:**", md)

    def test_render_project_status_markdown_not_a_repo(self):
        payload = (
            '{"path": "/tmp", "is_git_repo": false, "branch": "", '
            '"commit_hash": "", "has_uncommitted": false, "has_staged": false, '
            '"has_untracked": false, "has_modified": false, '
            '"uncommitted_count": 0, "files": [], "error": null}'
        )
        with patch(
            "project_manager.agent_project_manager_toolkit.check_git_status",
            return_value=payload,
        ):
            md = self.view.render_project_status_markdown()

        self.assertIn("not a Git repository", md)

    def test_render_project_summary_markdown(self):
        payload = (
            '{"workspace_path": "/ws", "total_projects": 1, '
            '"project_types": {"Python": ["demo"]}, '
            '"projects": [{"name": "demo", "type": "Python", "confidence": 0.9, '
            '"git_repo": true, "has_actions": false}]}'
        )
        with patch(
            "project_manager.agent_project_manager_toolkit.get_workspace_summary",
            return_value=payload,
        ):
            md = self.view.render_project_summary_markdown()

        self.assertIn("demo", md)
        self.assertIn("Python", md)
        self.assertIn("/ws", md)

    def test_handle_project_command_markdown_dispatch(self):
        payload = '{"workspace_path": "/ws", "count": 0, "projects": []}'
        with patch(
            "project_manager.agent_project_manager_toolkit.list_projects",
            return_value=payload,
        ):
            md = self.view.handle_project_command_markdown("\\projects")

        self.assertIsNotNone(md)
        self.assertIn("Registered Projects", md)

    def test_handle_project_command_markdown_returns_none_for_other(self):
        self.assertIsNone(self.view.handle_project_command_markdown("\\stats"))


# ---------------------------------------------------------------------------
# Chat history view
# ---------------------------------------------------------------------------

class TestChatHistoryView(unittest.TestCase):
    """Tests for components.tui.chat_history_view."""

    def setUp(self):
        from components.tui import chat_history_view

        self.view = chat_history_view

    def _fake_manager(self, sessions=None, active=None):
        """Build a mock ChatHistoryManager."""
        manager = MagicMock()
        manager.is_initialized = True
        manager.current_user.username = "tester"
        manager.list_sessions.return_value = sessions or []
        manager.get_active_session.return_value = active
        return manager

    def _fake_session(self, name="General Chat", sid="sid-1", stype="general"):
        session = MagicMock()
        session.session_name = name
        session.session_id = sid
        session.session_type.value = stype
        session.chat_key = "chat-general-tester"
        session.created_at.strftime.return_value = "2026-01-01 00:00"
        session.updated_at.strftime.return_value = "2026-01-01 00:00"
        return session

    def test_render_chat_sessions_markdown(self):
        session = self._fake_session()
        manager = self._fake_manager(sessions=[session], active=session)
        md = self.view.render_chat_sessions_markdown(manager)

        self.assertIn("General Chat", md)
        self.assertIn("sid-1", md)
        self.assertIn("tester", md)

    def test_render_chat_sessions_markdown_empty(self):
        manager = self._fake_manager(sessions=[])
        md = self.view.render_chat_sessions_markdown(manager)
        self.assertIn("No sessions found", md)

    def test_render_chat_sessions_markdown_uninitialized(self):
        manager = MagicMock()
        manager.is_initialized = False
        md = self.view.render_chat_sessions_markdown(manager)
        self.assertIn("not initialized", md)

    def test_render_chat_info_markdown(self):
        session = self._fake_session()
        manager = self._fake_manager(active=session)
        md = self.view.render_chat_info_markdown(manager)

        self.assertIn("General Chat", md)
        self.assertIn("sid-1", md)
        self.assertIn("general", md)

    def test_render_chat_info_markdown_no_session(self):
        manager = self._fake_manager(active=None)
        md = self.view.render_chat_info_markdown(manager)
        self.assertIn("No active session", md)

    def test_render_command_result_markdown(self):
        md = self.view.render_command_result_markdown("\\chat-info", "all good")
        self.assertIn("\\chat-info", md)
        self.assertIn("all good", md)

    def test_handle_chat_command_markdown_non_chat_command(self):
        self.assertIsNone(self.view.handle_chat_command_markdown("\\stats"))

    def test_handle_chat_command_markdown_dispatches(self):
        with patch(
            "chat_manager.commands.handler.handle_chat_command",
            return_value="done",
        ):
            md = self.view.handle_chat_command_markdown("\\chat-clear")

        self.assertIn("done", md)
        self.assertIn("\\chat-clear", md)


# ---------------------------------------------------------------------------
# TUI state bridge additions
# ---------------------------------------------------------------------------

class TestTuiStateProjectAndChat(unittest.TestCase):
    """TuiState must expose project and chat session context."""

    def setUp(self):
        from components.tui.state_bridge import TuiState

        self.state = TuiState()

    def test_update_project_context(self):
        self.state.update_project_context(
            project_name="demo",
            project_type="Python",
            project_path="/ws/demo",
            registered_projects=["demo", "other"],
        )
        self.assertEqual(self.state.active_project, "demo")
        self.assertEqual(self.state.project_type, "Python")
        self.assertEqual(self.state.project_path, "/ws/demo")
        self.assertEqual(self.state.registered_projects, ["demo", "other"])

    def test_update_chat_session(self):
        self.state.update_chat_session(
            session_name="General Chat",
            session_type="general",
            session_id="sid-9",
        )
        self.assertEqual(self.state.chat_session_name, "General Chat")
        self.assertEqual(self.state.chat_session_type, "general")
        self.assertEqual(self.state.chat_session_id, "sid-9")

    def test_initial_state_is_empty(self):
        self.assertEqual(self.state.active_project, "")
        self.assertEqual(self.state.chat_session_name, "")


# ---------------------------------------------------------------------------
# TUI app command dispatch
# ---------------------------------------------------------------------------

class TestTuiAppCommandDispatch(unittest.TestCase):
    """The TUI must route the new slash commands to the right handlers."""

    def _make_app(self):
        from components.tui.state_bridge import TuiState
        from components.tui.tui_app import TuiApp

        state = TuiState()
        app = TuiApp(
            agent=MagicMock(),
            prompt_handler_fn=MagicMock(),
            state=state,
            console=MagicMock(),
        )
        return app, state

    def test_app_accepts_feature_flags(self):
        app, _ = self._make_app()
        self.assertTrue(app.chat_history_enabled)
        self.assertTrue(app.project_manager_enabled)

    def test_tool_menu_renders_categories(self):
        app, state = self._make_app()
        app._render_tool_selection_menu()
        self.assertIn("Startup Tool Selection", state.markdown_content)

    def test_tool_list_renders(self):
        app, state = self._make_app()
        app._render_tool_list()
        self.assertIn("Available Tools", state.markdown_content)

    def test_tool_select_command_renders_result(self):
        app, state = self._make_app()
        app._handle_tool_select_command("\\tool-select 1")
        self.assertIn("Tool Selection Result", state.markdown_content)

    def test_tool_select_command_requires_argument(self):
        app, state = self._make_app()
        app._handle_tool_select_command("\\tool-select")
        self.assertIn("Usage", state.markdown_content)

    def test_tool_select_command_reports_invalid(self):
        app, state = self._make_app()
        app._handle_tool_select_command("\\tool-select abc")
        self.assertIn("Error", state.markdown_content)

    def test_project_command_renders_in_document(self):
        app, state = self._make_app()
        payload = '{"workspace_path": "/ws", "count": 0, "projects": []}'
        with patch(
            "project_manager.agent_project_manager_toolkit.list_projects",
            return_value=payload,
        ):
            app._handle_enter_pressed()  # not used; call dispatcher directly
            from components.tui.project_manager_view import (
                handle_project_command_markdown,
            )

            md = handle_project_command_markdown("\\projects")

        self.assertIn("Registered Projects", md)

    def test_help_text_mentions_new_commands(self):
        from components.tui.tui_app import HELP_TEXT

        for command in ("\\tools", "\\projects", "\\chat-sessions", "\\project-status"):
            self.assertIn(command, HELP_TEXT, f"{command} missing from HELP_TEXT")


# ---------------------------------------------------------------------------
# Prompt engine integration
# ---------------------------------------------------------------------------

class TestPromptEngineIntegration(unittest.TestCase):
    """The MW agent must build prompts with project context like the classic one."""

    def test_build_system_prompt_uses_prompt_engine(self):
        with patch.object(mw, "prompt_engine", MagicMock()) as engine:
            engine.generate_prompt.return_value = "PROMPTED"
            result = mw.build_system_prompt(user_input="hello")
            self.assertEqual(result, "PROMPTED")
            engine.generate_prompt.assert_called_once()

    def test_build_system_prompt_falls_back_to_static(self):
        with patch.object(mw, "PROMPT_INJECTION_ENABLED", False):
            with patch.object(mw, "build_project_context", return_value="CTX"):
                result = mw.build_system_prompt()
        self.assertIn("Torvalds", result)
        self.assertIn("CTX", result)

    def test_load_custom_template_missing_file(self):
        self.assertIsNone(mw._load_custom_template("/nonexistent/template.txt"))

    def test_load_custom_template_reads_file(self):
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as handle:
            handle.write("CUSTOM TEMPLATE")
            temp_path = handle.name

        try:
            self.assertEqual(mw._load_custom_template(temp_path), "CUSTOM TEMPLATE")
        finally:
            os.unlink(temp_path)

    def test_load_custom_template_empty_path(self):
        self.assertIsNone(mw._load_custom_template(""))


# ---------------------------------------------------------------------------
# Chat manager shutdown helper
# ---------------------------------------------------------------------------

class TestChatManagerShutdown(unittest.TestCase):
    """The shutdown helper must be safe to call at any time."""

    def test_shutdown_chat_manager_handles_missing_manager(self):
        with patch("chat_manager.startup.shutdown_chat_manager") as shutdown:
            mw._shutdown_chat_manager()
            shutdown.assert_called_once()

    def test_shutdown_chat_manager_swallows_errors(self):
        with patch(
            "chat_manager.startup.shutdown_chat_manager",
            side_effect=RuntimeError("boom"),
        ):
            mw._shutdown_chat_manager()  # must not raise


if __name__ == "__main__":
    unittest.main()
