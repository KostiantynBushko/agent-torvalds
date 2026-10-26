"""Tests for the user-settings API and the ``\\chat-user`` command.

The API is the piece the investigation report called defect **C1** (no public
way to change a user preference) and **C2** (a changed value never reached the
live buffer).  The command is the surface the operator uses.
"""

import unittest
from unittest.mock import patch

from chat_manager.commands import (
    cmd_chat_user,
    cmd_chat_user_get,
    cmd_chat_user_help,
    cmd_chat_user_set,
)
from chat_manager.commands.handler import handle_chat_command, is_chat_command
from chat_manager.manager import ChatHistoryManager
from chat_manager.settings import (
    DEFAULT_CHAT_TOKEN_LIMIT,
    MAX_CHAT_TOKEN_LIMIT,
    MIN_CHAT_TOKEN_LIMIT,
    SettingError,
)
from chat_manager.user import User


class TestUserSettingsApi(unittest.TestCase):
    """Tests for ChatHistoryManager.get_user_settings/update_user_settings."""

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

    def test_get_user_settings_returns_the_defaults(self):
        """A freshly provisioned user has the default chat-token limit."""
        settings = self.manager.get_user_settings()
        self.assertEqual(settings.chat_token_limit, DEFAULT_CHAT_TOKEN_LIMIT)
        self.assertEqual(settings.backend_type, "postgres")

    def test_get_user_settings_requires_initialization(self):
        """The API refuses to answer before the manager is initialized."""
        manager = ChatHistoryManager(
            storage_uri="sqlite:///:memory:",
            llama_uri="sqlite:///:memory:",
        )
        with self.assertRaises(RuntimeError):
            manager.get_user_settings()

    def test_update_user_settings_persists_the_change(self):
        """A new limit survives a fresh read of the user record."""
        self.manager.update_user_settings(chat_token_limit=12000)

        stored = self.manager._db.get_user_by_username("tester")
        self.assertEqual(stored.chat_token_limit, 12000)

    def test_update_user_settings_returns_the_new_values(self):
        """The API returns the updated snapshot."""
        settings = self.manager.update_user_settings(chat_token_limit=9000)
        self.assertEqual(settings.chat_token_limit, 9000)
        self.assertEqual(self.manager.get_user_settings().chat_token_limit, 9000)

    def test_update_user_settings_accepts_the_deprecated_alias(self):
        """The pre-rename key still works."""
        settings = self.manager.update_user_settings(token_limit=8000)
        self.assertEqual(settings.chat_token_limit, 8000)
        self.assertEqual(
            self.manager._db.get_user_by_username("tester").chat_token_limit, 8000
        )

    def test_update_user_settings_rejects_an_out_of_range_value(self):
        """A value outside the bounds is refused and nothing is written."""
        with self.assertRaises(SettingError):
            self.manager.update_user_settings(chat_token_limit=1)

        self.assertEqual(
            self.manager.get_user_settings().chat_token_limit,
            DEFAULT_CHAT_TOKEN_LIMIT,
        )

    def test_update_user_settings_rejects_a_non_numeric_value(self):
        """A non-numeric value is refused."""
        with self.assertRaises(SettingError):
            self.manager.update_user_settings(chat_token_limit="banana")

    def test_update_user_settings_rejects_an_unknown_key(self):
        """An unknown key is refused."""
        with self.assertRaises(SettingError):
            self.manager.update_user_settings(nonsense=1)

    def test_update_user_settings_rejects_a_read_only_key(self):
        """A read-only setting is refused."""
        with self.assertRaises(SettingError):
            self.manager.update_user_settings(backend_type="mysql")

    def test_update_user_settings_without_changes_is_a_no_op(self):
        """Calling the API with nothing to change returns the current state."""
        settings = self.manager.update_user_settings()
        self.assertEqual(settings.chat_token_limit, DEFAULT_CHAT_TOKEN_LIMIT)

    def test_changed_limit_reaches_the_live_buffer(self):
        """A changed limit takes effect without a session switch (defect C2)."""
        buffer = self.manager.get_memory_buffer()
        self.assertEqual(buffer.token_limit, DEFAULT_CHAT_TOKEN_LIMIT)

        self.manager.update_user_settings(chat_token_limit=20000)

        self.assertEqual(self.manager.get_memory_buffer().token_limit, 20000)

    def test_changed_limit_reaches_a_buffer_built_afterwards(self):
        """A buffer built after the change uses the new limit."""
        self.manager.update_user_settings(chat_token_limit=15000)
        self.assertEqual(self.manager.get_memory_buffer().token_limit, 15000)

    def test_get_memory_buffer_honours_the_override(self):
        """The override argument is honoured, not silently dropped (defect C3)."""
        first = self.manager.get_memory_buffer(chat_token_limit=111)
        self.assertEqual(first.token_limit, 111)

        second = self.manager.get_memory_buffer(chat_token_limit=222)
        self.assertEqual(second.token_limit, 222)
        self.assertIsNot(first, second)

    def test_get_memory_buffer_accepts_the_deprecated_override(self):
        """The deprecated override keyword still works."""
        buffer = self.manager.get_memory_buffer(token_limit=333)
        self.assertEqual(buffer.token_limit, 333)

    def test_set_chat_token_limit_helper(self):
        """The convenience wrapper changes the limit."""
        settings = self.manager.set_chat_token_limit(6400)
        self.assertEqual(settings.chat_token_limit, 6400)


class TestUserDataclassRename(unittest.TestCase):
    """Tests for the renamed User field and its compatibility seams."""

    def test_canonical_field(self):
        """The field carries the new name."""
        user = User(username="tester", chat_token_limit=4096)
        self.assertEqual(user.chat_token_limit, 4096)

    def test_deprecated_property_reads_and_writes(self):
        """The old attribute name still works, both ways."""
        user = User(username="tester", chat_token_limit=4096)
        self.assertEqual(user.token_limit, 4096)

        user.token_limit = 1234
        self.assertEqual(user.chat_token_limit, 1234)

    def test_deprecated_constructor_keyword(self):
        """The old constructor keyword still works."""
        user = User(username="tester", token_limit=2048)
        self.assertEqual(user.chat_token_limit, 2048)

    def test_both_constructor_keywords_is_an_error(self):
        """Passing both keywords is refused."""
        with self.assertRaises(TypeError):
            User(username="tester", chat_token_limit=1, token_limit=2)

    def test_to_dict_carries_both_keys(self):
        """The serialised form carries the canonical and the legacy key."""
        data = User(username="tester", chat_token_limit=77).to_dict()
        self.assertEqual(data["chat_token_limit"], 77)
        self.assertEqual(data["token_limit"], 77)

    def test_from_dict_accepts_either_key(self):
        """Deserialisation accepts the canonical and the legacy key."""
        canonical = User.from_dict(
            {"user_id": "u1", "username": "a", "chat_token_limit": 500}
        )
        legacy = User.from_dict(
            {"user_id": "u1", "username": "a", "token_limit": 500}
        )
        self.assertEqual(canonical.chat_token_limit, 500)
        self.assertEqual(legacy.chat_token_limit, 500)

    def test_from_dict_prefers_the_canonical_key(self):
        """When both keys are present, the canonical one wins."""
        user = User.from_dict(
            {
                "user_id": "u1",
                "username": "a",
                "chat_token_limit": 111,
                "token_limit": 222,
            }
        )
        self.assertEqual(user.chat_token_limit, 111)


class TestChatUserCommand(unittest.TestCase):
    """Tests for the \\chat-user command functions."""

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

    def test_shows_every_setting(self):
        """\\chat-user lists the settings and their values."""
        result = cmd_chat_user(self.manager)
        self.assertIn("chat_token_limit", result)
        self.assertIn("tester", result)
        self.assertIn(str(DEFAULT_CHAT_TOKEN_LIMIT), result)

    def test_get_one_setting(self):
        """\\chat-user get <key> shows a single value."""
        result = cmd_chat_user_get(self.manager, "chat_token_limit")
        self.assertIn(str(DEFAULT_CHAT_TOKEN_LIMIT), result)
        self.assertIn("chat_token_limit", result)

    def test_get_accepts_the_deprecated_alias(self):
        """\\chat-user get token_limit still works."""
        result = cmd_chat_user_get(self.manager, "token_limit")
        self.assertIn(str(DEFAULT_CHAT_TOKEN_LIMIT), result)

    def test_get_rejects_an_unknown_key(self):
        """An unknown key is reported, not raised."""
        result = cmd_chat_user_get(self.manager, "nonsense")
        self.assertIn("Unknown setting", result)

    def test_set_changes_the_value(self):
        """\\chat-user set <key> <value> changes the setting."""
        result = cmd_chat_user_set(self.manager, "chat_token_limit", "12000")
        self.assertIn("12000", result)
        self.assertEqual(self.manager.get_user_settings().chat_token_limit, 12000)

    def test_set_accepts_the_deprecated_alias(self):
        """\\chat-user set token_limit still works and names the new key."""
        result = cmd_chat_user_set(self.manager, "token_limit", "9000")
        self.assertIn("chat_token_limit", result)
        self.assertEqual(self.manager.get_user_settings().chat_token_limit, 9000)

    def test_set_reports_an_invalid_value(self):
        """An invalid value is reported, not raised."""
        result = cmd_chat_user_set(self.manager, "chat_token_limit", "5")
        self.assertIn(str(MIN_CHAT_TOKEN_LIMIT), result)
        self.assertEqual(
            self.manager.get_user_settings().chat_token_limit,
            DEFAULT_CHAT_TOKEN_LIMIT,
        )

    def test_set_reports_an_unknown_key(self):
        """An unknown key is reported, not raised."""
        result = cmd_chat_user_set(self.manager, "nonsense", "1")
        self.assertIn("Unknown setting", result)

    def test_set_rejects_a_read_only_setting(self):
        """A read-only setting is reported, not raised."""
        result = cmd_chat_user_set(self.manager, "backend_type", "mysql")
        self.assertIn("read-only", result)

    def test_help_lists_the_settings(self):
        """\\chat-user help describes the settings and their ranges."""
        result = cmd_chat_user_help(self.manager)
        self.assertIn("chat_token_limit", result)
        self.assertIn(str(MIN_CHAT_TOKEN_LIMIT), result)
        self.assertIn(str(MAX_CHAT_TOKEN_LIMIT), result)

    def test_commands_report_an_uninitialized_manager(self):
        """Every command refuses to run against an uninitialized manager."""
        manager = ChatHistoryManager(
            storage_uri="sqlite:///:memory:",
            llama_uri="sqlite:///:memory:",
        )
        for result in (
            cmd_chat_user(manager),
            cmd_chat_user_get(manager, "chat_token_limit"),
            cmd_chat_user_set(manager, "chat_token_limit", "1000"),
            cmd_chat_user_help(manager),
        ):
            self.assertIn("not initialized", result)


class TestChatUserDispatch(unittest.TestCase):
    """Tests for the \\chat-user dispatch through the command handler."""

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

    def _dispatch(self, cmd):
        """Run a command against this test's manager."""
        with patch(
            "chat_manager.startup.get_chat_manager", return_value=self.manager
        ):
            return handle_chat_command(cmd)

    def test_is_a_chat_command(self):
        """\\chat-user and its forms are recognised as chat commands."""
        for cmd in (
            "\\chat-user",
            "\\chat-user get chat_token_limit",
            "\\chat-user set chat_token_limit 12000",
            "\\chat-user help",
        ):
            self.assertTrue(is_chat_command(cmd), cmd)

    def test_shows_the_settings(self):
        """The bare command shows every setting."""
        result = self._dispatch("\\chat-user")
        self.assertIn("chat_token_limit", result)

    def test_set_and_get(self):
        """A value can be set and read back through the dispatcher."""
        self._dispatch("\\chat-user set chat_token_limit 12345")
        result = self._dispatch("\\chat-user get chat_token_limit")
        self.assertIn("12345", result)

    def test_set_without_a_value_reports_the_usage(self):
        """A missing value is reported with the usage line."""
        result = self._dispatch("\\chat-user set chat_token_limit")
        self.assertIn("Usage", result)

    def test_get_without_a_key_reports_the_usage(self):
        """A missing key is reported with the usage line."""
        result = self._dispatch("\\chat-user get")
        self.assertIn("Usage", result)

    def test_unknown_subcommand_is_reported(self):
        """An unknown subcommand is reported with the usage line."""
        result = self._dispatch("\\chat-user frobnicate")
        self.assertIn("Unknown subcommand", result)

    def test_help_is_dispatched(self):
        """The help subcommand is dispatched."""
        result = self._dispatch("\\chat-user help")
        self.assertIn("chat_token_limit", result)


if __name__ == "__main__":
    unittest.main()
