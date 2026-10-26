"""
Integration tests for the ``\\chat-user`` command and the user-settings API.

The command must be reachable the way every other interactive command is
reachable:

  - declared in the central command registry, so ``\\help`` lists it
  - dispatched by the chat command handler of the chat_manager module
  - rendered by the multi-window TUI
  - advertised by both orchestrators

Run with:
    pytest tests/test_user_settings_command.py -v
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
# The chat_manager module exposes the API
# ---------------------------------------------------------------------------

class TestChatManagerPublicApi(unittest.TestCase):
    """The settings API must be part of the chat_manager public surface."""

    def test_package_exports_the_settings(self):
        """``chat_manager`` exports the settings type and its constants."""
        import chat_manager

        for name in (
            "UserSettings",
            "SettingError",
            "DEFAULT_CHAT_TOKEN_LIMIT",
            "MIN_CHAT_TOKEN_LIMIT",
            "MAX_CHAT_TOKEN_LIMIT",
        ):
            self.assertTrue(hasattr(chat_manager, name), name)
            self.assertIn(name, chat_manager.__all__)

    def test_manager_exposes_the_settings_api(self):
        """The manager exposes get/update_user_settings."""
        from chat_manager.manager import ChatHistoryManager

        for name in ("get_user_settings", "update_user_settings"):
            self.assertTrue(callable(getattr(ChatHistoryManager, name)), name)

    def test_commands_package_exports_the_command_functions(self):
        """The command functions are exported by ``chat_manager.commands``."""
        import chat_manager.commands as commands

        for name in (
            "cmd_chat_user",
            "cmd_chat_user_get",
            "cmd_chat_user_set",
            "cmd_chat_user_help",
        ):
            self.assertTrue(callable(getattr(commands, name)), name)


# ---------------------------------------------------------------------------
# The command registry
# ---------------------------------------------------------------------------

class TestChatUserInTheRegistry(unittest.TestCase):
    """The command is declared where every other command is declared."""

    def setUp(self):
        from components import command_registry

        self.registry = command_registry

    def test_the_command_is_registered(self):
        """\\chat-user is in the registry, in the Chat category."""
        spec = self.registry.find_command("\\chat-user")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.category, "Chat")
        self.assertEqual(spec.feature, self.registry.FEATURE_CHAT_HISTORY)

    def test_the_help_output_lists_the_command(self):
        """The rendered help mentions the command."""
        text = self.registry.build_help_text()
        self.assertIn("\\chat-user", text)

        markdown = self.registry.build_help_markdown()
        self.assertIn("\\chat-user", markdown)

    def test_the_registry_and_the_handler_agree(self):
        """Every command the handler knows is declared in the registry."""
        from chat_manager.commands.handler import CHAT_COMMANDS

        registered = {
            name
            for spec in self.registry.get_command_specs(
                self.registry.HelpOptions(chat_history=True)
            )
            if spec.feature == self.registry.FEATURE_CHAT_HISTORY
            for name in (spec.name,) + spec.aliases
        }
        for command in CHAT_COMMANDS:
            self.assertIn(command, registered, command)

    def test_the_registry_and_the_handler_agree_the_other_way_round(self):
        """Every registered chat command is handled by the chat manager."""
        from chat_manager.commands.handler import CHAT_COMMANDS

        registered = {
            spec.name
            for spec in self.registry.get_command_specs(
                self.registry.HelpOptions(chat_history=True)
            )
            if spec.feature == self.registry.FEATURE_CHAT_HISTORY
        }
        for command in registered:
            self.assertIn(command, CHAT_COMMANDS, command)


# ---------------------------------------------------------------------------
# The dispatcher
# ---------------------------------------------------------------------------

class TestChatUserDispatch(unittest.TestCase):
    """The command is dispatched before the LLM is invoked."""

    def setUp(self):
        from chat_manager.commands.handler import is_chat_command

        self.is_chat_command = is_chat_command

    def test_every_form_is_recognised(self):
        """All forms of the command are chat commands."""
        for cmd in (
            "\\chat-user",
            "\\chat-user get chat_token_limit",
            "\\chat-user set chat_token_limit 12000",
            "\\chat-user help",
        ):
            self.assertTrue(self.is_chat_command(cmd), cmd)

    def test_a_similar_command_is_not_a_chat_command(self):
        """A command that merely starts with the same letters is not one."""
        for cmd in ("\\chat-users", "\\chat-userx", "\\chat-username"):
            self.assertFalse(self.is_chat_command(cmd), cmd)

    def test_the_handler_returns_a_response(self):
        """The handler answers with a user-facing string."""
        from chat_manager.commands.handler import handle_chat_command

        manager = MagicMock()
        manager.is_initialized = True
        manager.current_user.username = "tester"
        manager.get_user_settings.return_value.chat_token_limit = 5000
        manager.get_user_settings.return_value.backend_type = "postgres"
        manager.get_user_settings.return_value.as_rows.return_value = ()

        with patch("chat_manager.startup.get_chat_manager", return_value=manager):
            result = handle_chat_command("\\chat-user")

        self.assertIsInstance(result, str)
        self.assertIn("tester", result)


# ---------------------------------------------------------------------------
# The TUI rendering
# ---------------------------------------------------------------------------

class TestChatUserTuiView(unittest.TestCase):
    """The multi-window TUI renders the settings."""

    def setUp(self):
        from components.tui import chat_history_view

        self.view = chat_history_view

    def _fake_manager(self, limit=5000):
        """Build a mock ChatHistoryManager with settings."""
        from chat_manager.settings import UserSettings

        manager = MagicMock()
        manager.is_initialized = True
        manager.current_user.username = "tester"
        manager.get_user_settings.return_value = UserSettings(
            chat_token_limit=limit, backend_type="postgres"
        )
        return manager

    def test_the_settings_are_rendered(self):
        """The Markdown shows the user and the values."""
        md = self.view.render_chat_user_markdown(self._fake_manager(12000))

        self.assertIn("User Settings", md)
        self.assertIn("tester", md)
        self.assertIn("chat_token_limit", md)
        self.assertIn("12000", md)

    def test_an_uninitialized_manager_is_reported(self):
        """An uninitialized manager is reported, not raised."""
        manager = MagicMock()
        manager.is_initialized = False

        md = self.view.render_chat_user_markdown(manager)
        self.assertIn("not initialized", md)

    def test_the_command_is_dispatched_to_the_rich_rendering(self):
        """\\chat-user goes through the dedicated renderer."""
        with patch(
            "chat_manager.startup.get_chat_manager", return_value=self._fake_manager()
        ):
            md = self.view.handle_chat_command_markdown("\\chat-user")

        self.assertIn("User Settings", md)
        self.assertIn("chat_token_limit", md)


# ---------------------------------------------------------------------------
# The orchestrators
# ---------------------------------------------------------------------------

class TestOrchestratorsAdvertiseTheCommand(unittest.TestCase):
    """Both orchestrators tell the operator the command exists."""

    def _read(self, filename: str) -> str:
        return (ROOT / filename).read_text(encoding="utf-8")

    def test_the_classic_repl_mentions_the_command(self):
        """agent-torvalds.py advertises \\chat-user."""
        source = self._read("agent-torvalds.py")
        self.assertIn("\\chat-user", source)

    def test_the_multi_window_agent_mentions_the_command(self):
        """agent-torvalds-mw.py advertises \\chat-user."""
        source = self._read("agent-torvalds-mw.py")
        self.assertIn("\\chat-user", source)

    def test_both_orchestrators_dispatch_chat_commands(self):
        """Both orchestrators route \\chat-* through the chat handler."""
        for filename in ("agent-torvalds.py", "agent-torvalds-mw.py"):
            source = self._read(filename)
            self.assertIn("is_chat_command", source, filename)
            self.assertIn("handle_chat_command", source, filename)


if __name__ == "__main__":
    unittest.main()
