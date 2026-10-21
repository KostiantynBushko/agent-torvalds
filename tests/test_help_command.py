"""
Unit tests for the central interactive command registry and the ``\\help``
command.

Covers:
  - The registry itself (lookup, filtering, rendering)
  - The ``\\help`` command in the multi-window TUI
  - The ``\\help`` command in the classic REPL orchestrators

Run with:
    pytest tests/test_help_command.py -v
"""
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure the repository root is on the path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load_module(name: str, filename: str):
    """Load a script-style module (e.g. ``agent-torvalds.py``) by path."""
    path = ROOT / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Command registry
# ---------------------------------------------------------------------------

class TestCommandRegistry(unittest.TestCase):
    """The registry must describe every command exactly once."""

    def setUp(self):
        from components import command_registry

        self.registry = command_registry

    def test_help_command_is_registered(self):
        self.assertTrue(self.registry.is_help_command("\\help"))
        self.assertTrue(self.registry.is_help_command("\\HELP"))
        self.assertTrue(self.registry.is_help_command("  \\help  "))
        self.assertFalse(self.registry.is_help_command("\\stats"))
        self.assertFalse(self.registry.is_help_command("help"))
        self.assertFalse(self.registry.is_help_command(""))
        self.assertFalse(self.registry.is_help_command(None))

    def test_command_names_are_unique(self):
        names = [spec.name for spec in self.registry.COMMAND_SPECS]
        self.assertEqual(len(names), len(set(names)), "duplicate command names")

    def test_every_command_has_a_description(self):
        for spec in self.registry.COMMAND_SPECS:
            self.assertTrue(spec.name.startswith("\\"), f"{spec.name} missing backslash")
            self.assertTrue(spec.description, f"{spec.name} missing description")
            self.assertTrue(spec.usage, f"{spec.name} missing usage")

    def test_aliases_do_not_collide_with_commands(self):
        command_names = {spec.name.lower() for spec in self.registry.COMMAND_SPECS}
        for spec in self.registry.COMMAND_SPECS:
            for alias in spec.aliases:
                self.assertNotIn(
                    alias.lower(),
                    command_names,
                    f"alias {alias} collides with a real command",
                )

    def test_find_command_by_name_and_alias(self):
        options = self.registry.HelpOptions(tui=True)

        spec = self.registry.find_command("\\exit", options)
        self.assertIsNotNone(spec)
        self.assertEqual(spec.name, "\\exit")

        alias = self.registry.find_command("\\quit", options)
        self.assertIsNotNone(alias)
        self.assertEqual(alias.name, "\\exit")

    def test_find_command_accepts_missing_backslash(self):
        options = self.registry.HelpOptions(tui=True)
        self.assertIsNotNone(self.registry.find_command("stats", options))

    def test_find_command_returns_none_for_unknown(self):
        options = self.registry.HelpOptions(tui=True)
        self.assertIsNone(self.registry.find_command("\\nope", options))
        self.assertIsNone(self.registry.find_command("", options))

    def test_feature_flags_filter_commands(self):
        """Disabled features must not appear in the help output."""
        without_chat = self.registry.HelpOptions(chat_history=False)
        names = {
            spec.name
            for spec in self.registry.get_command_specs(without_chat)
        }
        self.assertNotIn("\\chat-sessions", names)
        self.assertIn("\\stats", names)

        without_tui = self.registry.HelpOptions(tui=False)
        names = {
            spec.name
            for spec in self.registry.get_command_specs(without_tui)
        }
        self.assertNotIn("\\tools", names)
        self.assertNotIn("\\clear", names)

    def test_build_help_markdown_lists_commands_with_descriptions(self):
        options = self.registry.HelpOptions(tui=True, keyboard_shortcuts=True)
        md = self.registry.build_help_markdown(options)

        self.assertIn("# Torvalds AI Agent", md)
        for command in ("\\help", "\\stats", "\\exit", "\\toggle-hitl"):
            self.assertIn(command, md, f"{command} missing from help output")

        # Every visible command must be mentioned with its description
        for spec in self.registry.get_command_specs(options):
            self.assertIn(spec.name, md)
            self.assertIn(spec.description, md)

    def test_build_help_text_lists_commands_with_descriptions(self):
        options = self.registry.HelpOptions(tui=False)
        text = self.registry.build_help_text(options)

        self.assertIn("Torvalds AI Agent", text)
        for command in ("\\help", "\\stats", "\\exit"):
            self.assertIn(command, text, f"{command} missing from help output")

    def test_build_help_text_hides_disabled_features(self):
        options = self.registry.HelpOptions(chat_history=False, hitl=False)
        text = self.registry.build_help_text(options)

        self.assertNotIn("\\chat-sessions", text)
        self.assertNotIn("\\toggle-hitl", text)
        self.assertIn("\\stats", text)

    def test_help_output_mentions_every_chat_command(self):
        options = self.registry.HelpOptions(tui=True)
        md = self.registry.build_help_markdown(options)
        for command in (
            "\\chat-sessions",
            "\\chat-select",
            "\\chat-create",
            "\\chat-delete",
            "\\chat-rename",
            "\\chat-info",
            "\\chat-clear",
        ):
            self.assertIn(command, md, f"{command} missing from help output")

    def test_help_output_mentions_every_project_command(self):
        options = self.registry.HelpOptions(tui=True)
        md = self.registry.build_help_markdown(options)
        for command in (
            "\\projects",
            "\\project-info",
            "\\project-status",
            "\\project-summary",
        ):
            self.assertIn(command, md, f"{command} missing from help output")

    def test_keyboard_shortcuts_only_in_tui_mode(self):
        with_shortcuts = self.registry.build_help_markdown(
            self.registry.HelpOptions(tui=True, keyboard_shortcuts=True)
        )
        without_shortcuts = self.registry.build_help_markdown(
            self.registry.HelpOptions(tui=True, keyboard_shortcuts=False)
        )

        self.assertIn("Keyboard Navigation", with_shortcuts)
        self.assertIn("PgUp", with_shortcuts)
        self.assertNotIn("Keyboard Navigation", without_shortcuts)


# ---------------------------------------------------------------------------
# TUI help command
# ---------------------------------------------------------------------------

class TestTuiHelpCommand(unittest.TestCase):
    """The TUI must render the help screen into the document pane."""

    def _make_app(self, **kwargs):
        from components.tui.state_bridge import TuiState
        from components.tui.tui_app import TuiApp

        state = TuiState()
        app = TuiApp(
            agent=MagicMock(),
            prompt_handler_fn=MagicMock(),
            state=state,
            console=MagicMock(),
            **kwargs,
        )
        return app, state

    def test_help_text_constant_is_generated_from_registry(self):
        from components.tui.tui_app import HELP_TEXT

        self.assertIn("\\help", HELP_TEXT)
        self.assertIn("\\stats", HELP_TEXT)
        self.assertIn("Help & Commands", HELP_TEXT)

    def test_build_help_markdown_contains_all_tui_commands(self):
        app, _ = self._make_app()
        md = app._build_help_markdown()

        for command in (
            "\\help",
            "\\clear",
            "\\exit",
            "\\stats",
            "\\toggle-hitl",
            "\\tools",
            "\\tool-list",
            "\\tool-select",
            "\\projects",
            "\\project-info",
            "\\project-status",
            "\\project-summary",
            "\\chat-sessions",
            "\\chat-info",
        ):
            self.assertIn(command, md, f"{command} missing from TUI help output")

    def test_build_help_markdown_respects_feature_flags(self):
        app, _ = self._make_app(chat_history_enabled=False)
        md = app._build_help_markdown()

        self.assertNotIn("\\chat-sessions", md)
        self.assertIn("\\stats", md)

    def test_help_command_renders_into_document_pane(self):
        app, state = self._make_app()
        app.state.input_buffer = "\\help"
        app._handle_enter_pressed()

        self.assertIn("Help & Commands", state.markdown_content)
        self.assertIn("\\stats", state.markdown_content)

    def test_help_command_is_case_insensitive(self):
        app, state = self._make_app()
        app.state.input_buffer = "\\HELP"
        app._handle_enter_pressed()

        self.assertIn("Help & Commands", state.markdown_content)

    def test_help_command_clears_the_input_buffer(self):
        app, state = self._make_app()
        app.state.input_buffer = "\\help"
        app._handle_enter_pressed()

        self.assertEqual(state.input_buffer, "")

    def test_help_command_does_not_reach_the_agent(self):
        """A slash command must never be sent to the LLM."""
        app, state = self._make_app()
        app.state.input_buffer = "\\help"
        app._handle_enter_pressed()

        # The agent task must not have been created
        self.assertIsNone(app._active_query_task)

    def test_hitl_on_command_is_dispatched(self):
        """\\hitl-on must be routed to the runtime toggle."""
        import asyncio

        async def scenario():
            app, state = self._make_app(hitl_toggle=MagicMock())
            app.hitl_toggle.is_hitl_command = (
                lambda cmd: cmd.lower() == "\\hitl-on"
            )

            app.state.input_buffer = "\\hitl-on"
            app._handle_enter_pressed()

            # The HITL command is scheduled as a background task; give the
            # event loop a chance to run it.
            await asyncio.sleep(0)
            app.hitl_toggle.process_command.assert_called_once_with("\\hitl-on")

            # The command must never reach the agent as a query
            self.assertIsNone(app._active_query_task)

        asyncio.run(scenario())


# ---------------------------------------------------------------------------
# Classic REPL help command
# ---------------------------------------------------------------------------

class TestClassicAgentHelpCommand(unittest.TestCase):
    """The classic orchestrator must expose the same \\help command."""

    def setUp(self):
        self.classic = _load_module("agent_torvalds_classic_help", "agent-torvalds.py")

    def test_classic_agent_imports_the_registry(self):
        self.assertTrue(hasattr(self.classic, "is_help_command"))
        self.assertTrue(hasattr(self.classic, "render_help_text"))
        self.assertTrue(hasattr(self.classic, "build_help_text"))

    def test_render_help_text_prints_the_command_list(self):
        with patch.object(self.classic.console, "print") as printed:
            output = self.classic.render_help_text()

        self.assertTrue(printed.called)
        for command in ("\\help", "\\stats", "\\exit"):
            self.assertIn(command, output, f"{command} missing from classic help")

    def test_render_help_text_respects_feature_flags(self):
        with patch.object(self.classic.console, "print"):
            output = self.classic.render_help_text(
                chat_history_enabled=False,
                runtime_toggle_enabled=False,
            )

        self.assertNotIn("\\chat-sessions", output)
        self.assertNotIn("\\toggle-hitl", output)
        self.assertIn("\\stats", output)

    def test_classic_agent_dispatches_project_commands(self):
        """The classic REPL must understand \\projects, like the MW agent."""
        self.assertTrue(self.classic.is_project_command("\\projects"))
        self.assertTrue(self.classic.is_project_command("\\project-status"))


class TestMultiWindowClassicHelpCommand(unittest.TestCase):
    """The MW classic linear fallback must expose \\help as well."""

    def setUp(self):
        self.mw = _load_module("agent_torvalds_mw_help", "agent-torvalds-mw.py")

    def test_mw_agent_imports_the_registry(self):
        self.assertTrue(hasattr(self.mw, "is_help_command"))
        self.assertTrue(hasattr(self.mw, "render_help_text"))

    def test_render_help_text_prints_the_command_list(self):
        with patch.object(self.mw.console, "print") as printed:
            output = self.mw.render_help_text()

        self.assertTrue(printed.called)
        for command in ("\\help", "\\stats", "\\exit"):
            self.assertIn(command, output, f"{command} missing from MW classic help")


# ---------------------------------------------------------------------------
# Registry consistency with the real dispatchers
# ---------------------------------------------------------------------------

class TestRegistryMatchesDispatchers(unittest.TestCase):
    """Every registered command must be handled by a real dispatcher."""

    def test_hitl_commands_match_the_runtime_toggle(self):
        from components.command_registry import (
            FEATURE_HITL,
            HelpOptions,
            get_command_specs,
        )
        from components.hitl_runtime_toggle import HITL_COMMANDS

        registered = {
            spec.name
            for spec in get_command_specs(HelpOptions(hitl=True))
            if spec.feature == FEATURE_HITL
        }
        for command in HITL_COMMANDS:
            self.assertIn(
                command,
                registered,
                f"{command} is handled by the toggle but missing from the registry",
            )

    def test_chat_commands_match_the_chat_handler(self):
        from chat_manager.commands.handler import CHAT_COMMANDS
        from components.command_registry import (
            FEATURE_CHAT_HISTORY,
            HelpOptions,
            get_command_specs,
        )

        registered = {
            name
            for spec in get_command_specs(HelpOptions(chat_history=True))
            if spec.feature == FEATURE_CHAT_HISTORY
            for name in (spec.name,) + spec.aliases
        }
        for command in CHAT_COMMANDS:
            self.assertIn(
                command,
                registered,
                f"{command} is handled by the chat manager but missing from the registry",
            )

    def test_project_commands_match_the_project_view(self):
        from components.command_registry import (
            FEATURE_PROJECT_MANAGER,
            HelpOptions,
            get_command_specs,
        )
        from components.tui.project_manager_view import PROJECT_COMMANDS

        registered = {
            name
            for spec in get_command_specs(HelpOptions(project_manager=True))
            if spec.feature == FEATURE_PROJECT_MANAGER
            for name in (spec.name,) + spec.aliases
        }
        for command in PROJECT_COMMANDS:
            self.assertIn(
                command,
                registered,
                f"{command} is handled by the project view but missing from the registry",
            )

    def test_tool_commands_match_the_tool_selection_view(self):
        from components.command_registry import (
            FEATURE_TUI,
            HelpOptions,
            get_command_specs,
        )
        from components.tui.tool_selection_view import is_tool_selection_command

        registered = {
            spec.name
            for spec in get_command_specs(HelpOptions(tui=True))
            if spec.feature == FEATURE_TUI
        }
        for command in ("\\tools", "\\tool-list", "\\tool-select"):
            self.assertTrue(is_tool_selection_command(command))
            self.assertIn(command, registered)


if __name__ == "__main__":
    unittest.main()
