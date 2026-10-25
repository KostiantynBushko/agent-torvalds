"""Tests for the user settings module.

Covers the validation rules, the deprecated ``token_limit`` alias, and the
immutable ``UserSettings`` snapshot.
"""

import unittest

from chat_manager.settings import (
    DEFAULT_CHAT_TOKEN_LIMIT,
    MAX_CHAT_TOKEN_LIMIT,
    MIN_CHAT_TOKEN_LIMIT,
    SETTING_ALIASES,
    SETTING_SPECS,
    SETTINGS_BY_KEY,
    SettingError,
    UserSettings,
    normalize_setting_key,
    validate_chat_token_limit,
    validate_setting_value,
)
from chat_manager.user import User


class TestSettingKeys(unittest.TestCase):
    """Tests for the canonical / alias resolution of setting keys."""

    def test_canonical_keys_resolve_to_themselves(self):
        """A canonical key resolves to itself."""
        for key in SETTINGS_BY_KEY:
            self.assertEqual(normalize_setting_key(key), key)

    def test_deprecated_token_limit_resolves_to_chat_token_limit(self):
        """The pre-rename name still resolves to the canonical one."""
        self.assertEqual(
            normalize_setting_key("token_limit"), "chat_token_limit"
        )

    def test_aliases_are_case_and_dash_insensitive(self):
        """Keys are normalised before they are looked up."""
        self.assertEqual(normalize_setting_key("CHAT-TOKEN-LIMIT"), "chat_token_limit")
        self.assertEqual(normalize_setting_key("  Token_Limit  "), "chat_token_limit")

    def test_unknown_key_is_rejected(self):
        """An unknown key raises SettingError and names the known ones."""
        with self.assertRaises(SettingError) as ctx:
            normalize_setting_key("bogus")
        self.assertIn("chat_token_limit", str(ctx.exception))

    def test_empty_key_is_rejected(self):
        """An empty key raises SettingError."""
        for empty in ("", "   ", None):
            with self.assertRaises(SettingError):
                normalize_setting_key(empty)

    def test_every_alias_points_at_a_known_setting(self):
        """No alias dangles."""
        for alias, target in SETTING_ALIASES.items():
            self.assertIn(target, SETTINGS_BY_KEY, alias)


class TestChatTokenLimitValidation(unittest.TestCase):
    """Tests for the chat-token limit bounds."""

    def test_valid_values_are_accepted(self):
        """A number inside the range is accepted."""
        self.assertEqual(validate_chat_token_limit("12000"), 12000)
        self.assertEqual(validate_chat_token_limit(MIN_CHAT_TOKEN_LIMIT), MIN_CHAT_TOKEN_LIMIT)
        self.assertEqual(validate_chat_token_limit(MAX_CHAT_TOKEN_LIMIT), MAX_CHAT_TOKEN_LIMIT)

    def test_below_the_minimum_is_rejected(self):
        """A value below the minimum is rejected with a helpful message."""
        with self.assertRaises(SettingError) as ctx:
            validate_chat_token_limit(MIN_CHAT_TOKEN_LIMIT - 1)
        self.assertIn(str(MIN_CHAT_TOKEN_LIMIT), str(ctx.exception))

    def test_above_the_maximum_is_rejected(self):
        """A value above the maximum is rejected."""
        with self.assertRaises(SettingError) as ctx:
            validate_chat_token_limit(MAX_CHAT_TOKEN_LIMIT + 1)
        self.assertIn(str(MAX_CHAT_TOKEN_LIMIT), str(ctx.exception))

    def test_non_numeric_is_rejected(self):
        """A non-numeric value is rejected with a clear message."""
        for value in ("abc", "", "12.5.6", None):
            with self.assertRaises(SettingError):
                validate_chat_token_limit(value)


class TestValidateSettingValue(unittest.TestCase):
    """Tests for the generic value validation."""

    def test_chat_token_limit_is_validated(self):
        """The chat-token limit goes through its own validator."""
        self.assertEqual(
            validate_setting_value("chat_token_limit", "8000"), 8000
        )

    def test_read_only_setting_is_rejected(self):
        """A read-only setting cannot be written."""
        with self.assertRaises(SettingError) as ctx:
            validate_setting_value("backend_type", "mysql")
        self.assertIn("read-only", str(ctx.exception))

    def test_unknown_setting_is_rejected(self):
        """An unknown setting is rejected."""
        with self.assertRaises(SettingError):
            validate_setting_value("nonsense", "1")


class TestUserSettings(unittest.TestCase):
    """Tests for the UserSettings snapshot."""

    def test_from_user_reads_the_renamed_field(self):
        """The snapshot reads chat_token_limit from the user."""
        user = User(username="tester", chat_token_limit=9000)
        settings = UserSettings.from_user(user)
        self.assertEqual(settings.chat_token_limit, 9000)
        self.assertEqual(settings.backend_type, "postgres")

    def test_from_user_reads_the_deprecated_alias(self):
        """A user carrying only the old name still yields the right value."""
        user = User(username="tester")
        user.token_limit = 7000
        settings = UserSettings.from_user(user)
        self.assertEqual(settings.chat_token_limit, 7000)

    def test_from_none_yields_the_defaults(self):
        """A missing user yields the default settings."""
        settings = UserSettings.from_user(None)
        self.assertEqual(settings.chat_token_limit, DEFAULT_CHAT_TOKEN_LIMIT)

    def test_get_resolves_aliases(self):
        """Reading through the deprecated alias yields the same value."""
        settings = UserSettings(chat_token_limit=4242)
        self.assertEqual(settings.get("token_limit"), 4242)
        self.assertEqual(settings.get("chat_token_limit"), 4242)

    def test_to_dict_uses_the_canonical_key(self):
        """The serialised form uses the canonical key."""
        data = UserSettings(chat_token_limit=321).to_dict()
        self.assertEqual(data["chat_token_limit"], 321)
        self.assertEqual(data["backend_type"], "postgres")

    def test_as_rows_covers_every_spec(self):
        """Every known setting appears in the rows."""
        rows = UserSettings().as_rows()
        self.assertEqual(len(rows), len(SETTING_SPECS))
        self.assertEqual(
            {row[0] for row in rows}, set(SETTINGS_BY_KEY)
        )

    def test_snapshot_is_immutable(self):
        """The snapshot cannot be mutated by accident."""
        settings = UserSettings()
        with self.assertRaises(Exception):
            settings.chat_token_limit = 1


class TestSettingSpecs(unittest.TestCase):
    """Tests for the setting specifications themselves."""

    def test_chat_token_limit_is_writable_and_bounded(self):
        """The chat-token limit is a writable, bounded setting."""
        spec = SETTINGS_BY_KEY["chat_token_limit"]
        self.assertTrue(spec.writable)
        self.assertEqual(spec.minimum, MIN_CHAT_TOKEN_LIMIT)
        self.assertEqual(spec.maximum, MAX_CHAT_TOKEN_LIMIT)
        self.assertEqual(spec.default, DEFAULT_CHAT_TOKEN_LIMIT)
        self.assertEqual(spec.unit, "tokens")

    def test_backend_type_is_read_only(self):
        """The backend type is shown but not written at runtime."""
        spec = SETTINGS_BY_KEY["backend_type"]
        self.assertFalse(spec.writable)


if __name__ == "__main__":
    unittest.main()
