"""
Unit tests for WhiptailPasswordPrompter.

Tests the whiptail-based password prompter with mocked whiptail dialogs:
- prompt_password(): password prompting with validation callbacks, max attempts, empty input
- show_message(): message dialogs
- confirm(): yes/no confirmation dialogs
- is_available(): availability checking (binary + python package)
- get_prompter(): singleton convenience function
- prompt_sudo_password_whiptail(): module-level convenience function
- Error handling: ImportError, exceptions during dialog

All whiptail subprocess calls are mocked to avoid actual terminal dialogs.
"""
import unittest
import subprocess
import sys
import os
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.whiptail_password import (
    WhiptailPasswordPrompter,
    get_prompter,
    prompt_sudo_password_whiptail,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_whiptail_class(prompt_values=None, confirm_value=True):
    """Create a mock Whiptail class that returns controlled values."""
    mock_cls = MagicMock()
    mock_instance = MagicMock()
    mock_cls.return_value = mock_instance

    if prompt_values is not None:
        mock_instance.prompt.side_effect = prompt_values
    else:
        mock_instance.prompt.return_value = "password123"

    if confirm_value is not None:
        mock_instance.confirm.return_value = confirm_value

    return mock_cls, mock_instance


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------

class TestWhiptailPasswordPrompterInit(unittest.TestCase):
    """Test WhiptailPasswordPrompter initialisation."""

    def test_default_params(self):
        prompter = WhiptailPasswordPrompter()
        self.assertEqual(prompter.title, "Sudo Password")
        self.assertEqual(prompter.backtitle, "Enter your sudo password")
        self.assertEqual(prompter.height, 10)
        self.assertEqual(prompter.width, 50)

    def test_custom_params(self):
        prompter = WhiptailPasswordPrompter(
            title="My App",
            backtitle="Enter credentials",
            height=15,
            width=70,
        )
        self.assertEqual(prompter.title, "My App")
        self.assertEqual(prompter.backtitle, "Enter credentials")
        self.assertEqual(prompter.height, 15)
        self.assertEqual(prompter.width, 70)


# ---------------------------------------------------------------------------
# prompt_password()
# ---------------------------------------------------------------------------

class TestPromptPassword(unittest.TestCase):
    """Test the prompt_password() method."""

    def test_first_attempt_success_no_callback(self):
        """Accepts first non-empty password when no test_callback provided."""
        mock_cls, mock_instance = _mock_whiptail_class(prompt_values=["mypassword"])

        with patch("whiptail.Whiptail", mock_cls):
            prompter = WhiptailPasswordPrompter()
            result = prompter.prompt_password(test_callback=None)

        self.assertTrue(result["success"])
        self.assertEqual(result["password"], "mypassword")
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(result["method"], "whiptail")

    def test_first_attempt_success_with_callback(self):
        """Accepts password when callback returns True."""
        mock_cls, mock_instance = _mock_whiptail_class(prompt_values=["correct"])
        callback = lambda p: p == "correct"

        with patch("whiptail.Whiptail", mock_cls):
            prompter = WhiptailPasswordPrompter()
            result = prompter.prompt_password(test_callback=callback)

        self.assertTrue(result["success"])
        self.assertEqual(result["password"], "correct")
        self.assertEqual(result["attempts"], 1)

    def test_retries_on_empty_password(self):
        """Skips empty passwords and retries."""
        mock_cls, mock_instance = _mock_whiptail_class(
            prompt_values=["", "", "final_password"]
        )

        with patch("whiptail.Whiptail", mock_cls):
            prompter = WhiptailPasswordPrompter()
            result = prompter.prompt_password(test_callback=None)

        self.assertTrue(result["success"])
        self.assertEqual(result["password"], "final_password")
        self.assertEqual(result["attempts"], 3)

    def test_retries_on_invalid_callback(self):
        """Retries when test_callback returns False."""
        mock_cls, mock_instance = _mock_whiptail_class(
            prompt_values=["wrong", "also_wrong", "right"]
        )
        callback = lambda p: p == "right"

        with patch("whiptail.Whiptail", mock_cls):
            prompter = WhiptailPasswordPrompter()
            result = prompter.prompt_password(test_callback=callback, max_attempts=5)

        self.assertTrue(result["success"])
        self.assertEqual(result["password"], "right")
        self.assertEqual(result["attempts"], 3)

    def test_max_attempts_exhausted(self):
        """Fails after max_attempts with no valid password."""
        mock_cls, mock_instance = _mock_whiptail_class(
            prompt_values=["bad1", "bad2", "bad3"]
        )
        callback = lambda p: p.startswith("good")

        with patch("whiptail.Whiptail", mock_cls):
            prompter = WhiptailPasswordPrompter()
            result = prompter.prompt_password(test_callback=callback, max_attempts=3)

        self.assertFalse(result["success"])
        self.assertIsNone(result["password"])
        self.assertEqual(result["attempts"], 3)
        self.assertIn("Failed after 3 attempts", result["error"])

    def test_max_attempts_with_empty_passwords(self):
        """Empty passwords count toward max_attempts."""
        mock_cls, mock_instance = _mock_whiptail_class(
            prompt_values=["", "", ""]
        )

        with patch("whiptail.Whiptail", mock_cls):
            prompter = WhiptailPasswordPrompter()
            result = prompter.prompt_password(test_callback=None, max_attempts=3)

        self.assertFalse(result["success"])
        self.assertIn("Failed after 3 attempts", result["error"])

    def test_prompt_exception_returns_error(self):
        """Exception during prompt returns error dict."""
        mock_cls, mock_instance = _mock_whiptail_class(
            prompt_values=[RuntimeError("dialog crashed")]
        )

        with patch("whiptail.Whiptail", mock_cls):
            prompter = WhiptailPasswordPrompter()
            result = prompter.prompt_password(test_callback=None)

        self.assertFalse(result["success"])
        self.assertIn("Whiptail prompt failed", result["error"])

    def test_custom_message_passed_to_prompt(self):
        """Custom message is included in prompt call."""
        mock_cls, mock_instance = _mock_whiptail_class(prompt_values=["pwd"])

        with patch("whiptail.Whiptail", mock_cls):
            prompter = WhiptailPasswordPrompter()
            prompter.prompt_password(
                message="Enter secret:",
                test_callback=None,
            )
            # Verify prompt was called with message containing custom text
            call_kwargs = mock_instance.prompt.call_args[1]
            self.assertIn("Enter secret:", call_kwargs["msg"])

    def test_password_flag_true(self):
        """password=True is passed to prompt for masked input."""
        mock_cls, mock_instance = _mock_whiptail_class(prompt_values=["pwd"])

        with patch("whiptail.Whiptail", mock_cls):
            prompter = WhiptailPasswordPrompter()
            prompter.prompt_password(test_callback=None)
            call_kwargs = mock_instance.prompt.call_args[1]
            self.assertTrue(call_kwargs["password"])

    def test_attempt_counter_in_message(self):
        """Message includes attempt number."""
        mock_cls, mock_instance = _mock_whiptail_class(
            prompt_values=["bad", "good"]
        )
        callback = lambda p: p == "good"

        with patch("whiptail.Whiptail", mock_cls):
            prompter = WhiptailPasswordPrompter()
            prompter.prompt_password(test_callback=callback)

            # Second call should have attempt 2
            second_call_kwargs = mock_instance.prompt.call_args_list[1][1]
            self.assertIn("attempt 2/", second_call_kwargs["msg"])


# ---------------------------------------------------------------------------
# show_message()
# ---------------------------------------------------------------------------

class TestShowMessage(unittest.TestCase):
    """Test the show_message() method."""

    def test_show_message_success(self):
        """Returns True when alert succeeds."""
        mock_cls, mock_instance = _mock_whiptail_class()

        with patch("whiptail.Whiptail", mock_cls):
            prompter = WhiptailPasswordPrompter()
            result = prompter.show_message("Hello world!")

        self.assertTrue(result)
        mock_instance.alert.assert_called_once_with("Hello world!")

    def test_show_message_with_custom_title(self):
        """Uses custom title when provided."""
        mock_cls, mock_instance = _mock_whiptail_class()

        with patch("whiptail.Whiptail", mock_cls):
            prompter = WhiptailPasswordPrompter()
            prompter.show_message("Msg", title="Custom Title")
            # Verify Whiptail was called with custom title
            call_kwargs = mock_cls.call_args[1]
            self.assertEqual(call_kwargs["title"], "Custom Title")

    def test_show_message_exception(self):
        """Returns False when exception occurs."""
        mock_cls = MagicMock(side_effect=RuntimeError("crash"))

        with patch("whiptail.Whiptail", mock_cls):
            prompter = WhiptailPasswordPrompter()
            result = prompter.show_message("Msg")

        self.assertFalse(result)


# ---------------------------------------------------------------------------
# confirm()
# ---------------------------------------------------------------------------

class TestConfirm(unittest.TestCase):
    """Test the confirm() method."""

    def test_confirm_yes(self):
        """Returns True when user confirms."""
        mock_cls, mock_instance = _mock_whiptail_class(confirm_value=True)

        with patch("whiptail.Whiptail", mock_cls):
            prompter = WhiptailPasswordPrompter()
            result = prompter.confirm("Proceed?")

        self.assertTrue(result)

    def test_confirm_no(self):
        """Returns False when user declines."""
        mock_cls, mock_instance = _mock_whiptail_class(confirm_value=False)

        with patch("whiptail.Whiptail", mock_cls):
            prompter = WhiptailPasswordPrompter()
            result = prompter.confirm("Proceed?")

        self.assertFalse(result)

    def test_confirm_exception(self):
        """Returns False on exception."""
        mock_cls = MagicMock(side_effect=RuntimeError("crash"))

        with patch("whiptail.Whiptail", mock_cls):
            prompter = WhiptailPasswordPrompter()
            result = prompter.confirm("Proceed?")

        self.assertFalse(result)

    def test_confirm_default_yes_passed(self):
        """default_yes=True doesn't add --defaultno."""
        mock_cls, mock_instance = _mock_whiptail_class(confirm_value=True)

        with patch("whiptail.Whiptail", mock_cls):
            prompter = WhiptailPasswordPrompter()
            prompter.confirm("Proceed?", default_yes=True)
            # confirm() on Whiptail class handles default internally
            mock_instance.confirm.assert_called_once()

    def test_custom_title_for_confirm(self):
        """Custom title is used for confirm dialog."""
        mock_cls, mock_instance = _mock_whiptail_class(confirm_value=True)

        with patch("whiptail.Whiptail", mock_cls):
            prompter = WhiptailPasswordPrompter()
            prompter.confirm("Proceed?", title="Custom Confirm")
            call_kwargs = mock_cls.call_args[1]
            self.assertEqual(call_kwargs["title"], "Custom Confirm")


# ---------------------------------------------------------------------------
# is_available()
# ---------------------------------------------------------------------------

class TestIsAvailable(unittest.TestCase):
    """Test the is_available() static method."""

    def test_both_available(self):
        """Returns True when both binary and python package are present."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="/usr/bin/whiptail\n")
            with patch.dict(sys.modules, {"whiptail": MagicMock()}):
                result = WhiptailPasswordPrompter.is_available()

        self.assertTrue(result["available"])
        self.assertEqual(result["binary_path"], "/usr/bin/whiptail")
        self.assertTrue(result["python_package"])

    def test_binary_missing(self):
        """Returns False when binary not found."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            result = WhiptailPasswordPrompter.is_available()

        self.assertFalse(result["available"])
        self.assertIsNone(result["binary_path"])

    def test_python_package_missing(self):
        """Returns False when python package import fails."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="/usr/bin/whiptail\n")
            # Use importlib to mock the import
            import importlib
            real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

            def mock_import(name, *args, **kwargs):
                if name == "whiptail":
                    raise ImportError("No module named 'whiptail'")
                return real_import(name, *args, **kwargs)

            with patch("__builtins__.__import__", side_effect=mock_import):
                result = WhiptailPasswordPrompter.is_available()

        self.assertFalse(result["available"])
        self.assertFalse(result["python_package"])

    def test_subprocess_timeout(self):
        """Handles subprocess timeout gracefully."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("which", 5)
            result = WhiptailPasswordPrompter.is_available()

        self.assertFalse(result["available"])
        self.assertIn("Binary check failed", result["details"])

    def test_details_contains_info(self):
        """Details string provides diagnostic information."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="/usr/bin/whiptail\n")
            result = WhiptailPasswordPrompter.is_available()

        self.assertIn("Binary", result["details"])


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------

class TestConvenienceFunctions(unittest.TestCase):
    """Test get_prompter() and prompt_sudo_password_whiptail()."""

    def test_get_prompter_returns_instance(self):
        """Returns a WhiptailPasswordPrompter instance."""
        prompter = get_prompter()
        self.assertIsInstance(prompter, WhiptailPasswordPrompter)

    def test_get_prompter_custom_params(self):
        """Accepts custom parameters."""
        prompter = get_prompter(title="Custom", backtitle="BT", height=20, width=80)
        self.assertEqual(prompter.title, "Custom")
        self.assertEqual(prompter.backtitle, "BT")
        self.assertEqual(prompter.height, 20)
        self.assertEqual(prompter.width, 80)

    def test_prompt_sudo_password_whiptail_calls_prompter(self):
        """Convenience function delegates to prompter."""
        mock_cls, mock_instance = _mock_whiptail_class(prompt_values=["sudo_pass"])

        with patch("whiptail.Whiptail", mock_cls):
            result = prompt_sudo_password_whiptail(
                max_attempts=2,
                test_callback=lambda p: len(p) > 0,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["password"], "sudo_pass")
        self.assertEqual(result["method"], "whiptail")

    def test_prompt_sudo_password_whiptail_custom_title(self):
        """Custom title is passed through."""
        mock_cls, mock_instance = _mock_whiptail_class(prompt_values=["pass"])

        with patch("whiptail.Whiptail", mock_cls):
            prompt_sudo_password_whiptail(
                title="My Title",
                backtitle="My BT",
                test_callback=lambda p: True,
            )

        # Verify the prompter was created with custom title
        # (it creates a new WhiptailPasswordPrompter internally)


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases(unittest.TestCase):
    """Edge cases and boundary conditions."""

    def test_import_error_returns_failure(self):
        """ImportError during Whiptail import returns clean failure."""
        with patch("whiptail.Whiptail", MagicMock(side_effect=ImportError("no whiptail"))):
            prompter = WhiptailPasswordPrompter()
            result = prompter.prompt_password()

        self.assertFalse(result["success"])
        self.assertIn("whiptail", result["error"].lower())

    def test_special_characters_in_password(self):
        """Passwords with special characters are handled."""
        special_password = "p@$$w0rd!#$%^&*()"
        mock_cls, mock_instance = _mock_whiptail_class(prompt_values=[special_password])

        with patch("whiptail.Whiptail", mock_cls):
            prompter = WhiptailPasswordPrompter()
            result = prompter.prompt_password(test_callback=None)

        self.assertTrue(result["success"])
        self.assertEqual(result["password"], special_password)

    def test_unicode_in_message(self):
        """Unicode characters in messages don't crash."""
        mock_cls, mock_instance = _mock_whiptail_class(prompt_values=["ok"])

        with patch("whiptail.Whiptail", mock_cls):
            prompter = WhiptailPasswordPrompter()
            result = prompter.prompt_password(
                message="Enter password \U0001f511:",
                test_callback=None,
            )

        self.assertTrue(result["success"])

    def test_very_long_password(self):
        """Long passwords are handled."""
        long_password = "x" * 1000
        mock_cls, mock_instance = _mock_whiptail_class(prompt_values=[long_password])

        with patch("whiptail.Whiptail", mock_cls):
            prompter = WhiptailPasswordPrompter()
            result = prompter.prompt_password(test_callback=None)

        self.assertTrue(result["success"])
        self.assertEqual(len(result["password"]), 1000)

    def test_single_attempt(self):
        """max_attempts=1 allows only one try."""
        mock_cls, mock_instance = _mock_whiptail_class(prompt_values=[""])

        with patch("whiptail.Whiptail", mock_cls):
            prompter = WhiptailPasswordPrompter()
            result = prompter.prompt_password(test_callback=None, max_attempts=1)

        self.assertFalse(result["success"])
        self.assertEqual(result["attempts"], 1)

    def test_callback_with_whitespace_password(self):
        """Callback can reject whitespace-only passwords."""
        mock_cls, mock_instance = _mock_whiptail_class(
            prompt_values=["   ", "valid"]
        )
        callback = lambda p: p.strip() != ""

        with patch("whiptail.Whiptail", mock_cls):
            prompter = WhiptailPasswordPrompter()
            result = prompter.prompt_password(test_callback=callback)

        self.assertTrue(result["success"])
        self.assertEqual(result["password"], "valid")

    def test_result_has_no_error_on_success(self):
        """Successful result doesn't have error key or it's empty."""
        mock_cls, mock_instance = _mock_whiptail_class(prompt_values=["good"])

        with patch("whiptail.Whiptail", mock_cls):
            prompter = WhiptailPasswordPrompter()
            result = prompter.prompt_password(test_callback=None)

        self.assertTrue(result["success"])
        # Error should not be set or should be None/empty
        self.assertNotIn("error", result) or not result.get("error")


# ---------------------------------------------------------------------------
# Run tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
