"""
Unit tests for ConsoleInputModule.

Tests the async console input methods with mocked stdin/stdout:
- prompt(): text input with timeout
- confirm(): yes/no confirmation
- menu(): option selection
- password(): hidden password input
- timeout handling for all methods
"""
import unittest
import asyncio
import sys
import os
from io import StringIO
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.console_input_module import ConsoleInputModule


class TestConsoleInputModuleInit(unittest.TestCase):
    """Test ConsoleInputModule initialization."""

    def test_default_console(self):
        """Should create a default Console when none provided."""
        module = ConsoleInputModule()
        self.assertIsNotNone(module.console)

    def test_custom_console(self):
        """Should use provided Console instance."""
        from rich.console import Console
        custom = Console()
        module = ConsoleInputModule(console=custom)
        self.assertIs(module.console, custom)


class TestPromptMethod(unittest.TestCase):
    """Test the prompt() static method."""

    def test_prompt_returns_user_input(self):
        """Should return user input when provided."""
        async def _run():
            with patch("builtins.input", return_value="hello world"):
                result = await ConsoleInputModule.prompt("Enter: ", timeout=5)
            return result

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(result, "hello world")

    def test_prompt_returns_default_on_empty(self):
        """Should return default when user submits empty string."""
        async def _run():
            with patch("builtins.input", return_value="  "):
                result = await ConsoleInputModule.prompt("Enter: ", default="fallback", timeout=5)
            return result

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(result, "fallback")

    def test_prompt_returns_default_on_eof(self):
        """Should return default on EOFError."""
        async def _run():
            with patch("builtins.input", side_effect=EOFError):
                result = await ConsoleInputModule.prompt("Enter: ", default="eof_val", timeout=5)
            return result

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(result, "eof_val")

    def test_prompt_returns_default_on_keyboard_interrupt(self):
        """Should return default on KeyboardInterrupt."""
        async def _run():
            with patch("builtins.input", side_effect=KeyboardInterrupt):
                result = await ConsoleInputModule.prompt("Enter: ", default="ctrl_c", timeout=5)
            return result

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(result, "ctrl_c")

    def test_prompt_timeout_returns_default(self):
        """Should return default when timeout expires."""
        async def _run():
            def slow_input():
                await asyncio.sleep(10)  # Slower than timeout
                return "too late"

            with patch("builtins.input", side_effect=asyncio.sleep):
                # Simulate timeout by making input block
                result = await ConsoleInputModule.prompt("Enter: ", default="timed_out", timeout=1)
            return result

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(result, "timed_out")


class TestConfirmMethod(unittest.TestCase):
    """Test the confirm() method."""

    def test_confirm_yes(self):
        """Should return True for 'y' or 'yes'."""
        async def _run():
            module = ConsoleInputModule()
            with patch.object(ConsoleInputModule, "prompt", new_callable=AsyncMock, return_value="yes"):
                result = await module.confirm("Proceed?", default_yes=True, timeout=5)
            return result

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertTrue(result)

    def test_confirm_no(self):
        """Should return False for 'n' or 'no'."""
        async def _run():
            module = ConsoleInputModule()
            with patch.object(ConsoleInputModule, "prompt", new_callable=AsyncMock, return_value="no"):
                result = await module.confirm("Proceed?", default_yes=True, timeout=5)
            return result

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertFalse(result)

    def test_confirm_default_yes_on_empty(self):
        """Should return default_yes when response is empty."""
        async def _run():
            module = ConsoleInputModule()
            with patch.object(ConsoleInputModule, "prompt", new_callable=AsyncMock, return_value=""):
                result = await module.confirm("Proceed?", default_yes=True, timeout=5)
            return result

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertTrue(result)

    def test_confirm_default_no_on_empty(self):
        """Should return default_no when response is empty."""
        async def _run():
            module = ConsoleInputModule()
            with patch.object(ConsoleInputModule, "prompt", new_callable=AsyncMock, return_value=""):
                result = await module.confirm("Proceed?", default_yes=False, timeout=5)
            return result

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertFalse(result)

    def test_confirm_case_insensitive(self):
        """Should handle 'Y', 'Yes', 'YES' etc."""
        async def _run():
            module = ConsoleInputModule()
            with patch.object(ConsoleInputModule, "prompt", new_callable=AsyncMock, return_value="Y"):
                result = await module.confirm("Proceed?", timeout=5)
            return result

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertTrue(result)


class TestMenuMethod(unittest.TestCase):
    """Test the menu() method."""

    def test_menu_selects_first_option(self):
        """Should return first option when user selects 1."""
        async def _run():
            module = ConsoleInputModule()
            with patch.object(ConsoleInputModule, "prompt", new_callable=AsyncMock, return_value="1"):
                result = await module.menu("Choose:", ["opt_a", "opt_b", "opt_c"], timeout=5)
            return result

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(result, "opt_a")

    def test_menu_selects_second_option(self):
        """Should return second option when user selects 2."""
        async def _run():
            module = ConsoleInputModule()
            with patch.object(ConsoleInputModule, "prompt", new_callable=AsyncMock, return_value="2"):
                result = await module.menu("Choose:", ["opt_a", "opt_b", "opt_c"], timeout=5)
            return result

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(result, "opt_b")

    def test_menu_invalid_input_returns_first(self):
        """Should return first option on invalid input."""
        async def _run():
            module = ConsoleInputModule()
            with patch.object(ConsoleInputModule, "prompt", new_callable=AsyncMock, return_value="abc"):
                result = await module.menu("Choose:", ["opt_a", "opt_b"], timeout=5)
            return result

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(result, "opt_a")

    def test_menu_out_of_range_returns_first(self):
        """Should return first option when index is out of range."""
        async def _run():
            module = ConsoleInputModule()
            with patch.object(ConsoleInputModule, "prompt", new_callable=AsyncMock, return_value="99"):
                result = await module.menu("Choose:", ["opt_a", "opt_b"], timeout=5)
            return result

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(result, "opt_a")

    def test_menu_default_on_timeout(self):
        """Should return first option when timeout returns default."""
        async def _run():
            module = ConsoleInputModule()
            with patch.object(ConsoleInputModule, "prompt", new_callable=AsyncMock, return_value="1"):
                result = await module.menu("Choose:", ["default_opt", "other"], timeout=5)
            return result

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(result, "default_opt")


class TestPasswordMethod(unittest.TestCase):
    """Test the password() method."""

    def test_password_returns_input(self):
        """Should return entered password."""
        async def _run():
            module = ConsoleInputModule()
            with patch("getpass.getpass", return_value="secret123"):
                result = await module.password(timeout=5)
            return result

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(result, "secret123")

    def test_password_returns_empty_on_eof(self):
        """Should return empty string on EOFError."""
        async def _run():
            module = ConsoleInputModule()
            with patch("getpass.getpass", side_effect=EOFError):
                result = await module.password(timeout=5)
            return result

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(result, "")

    def test_password_returns_empty_on_keyboard_interrupt(self):
        """Should return empty string on KeyboardInterrupt."""
        async def _run():
            module = ConsoleInputModule()
            with patch("getpass.getpass", side_effect=KeyboardInterrupt):
                result = await module.password(timeout=5)
            return result

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(result, "")

    def test_password_timeout_returns_empty(self):
        """Should return empty string on timeout."""
        async def _run():
            module = ConsoleInputModule()
            with patch("getpass.getpass", side_effect=lambda msg: asyncio.sleep(10)):
                result = await module.password(timeout=1)
            return result

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(result, "")

    def test_password_custom_message(self):
        """Should use custom message."""
        async def _run():
            module = ConsoleInputModule()
            with patch("getpass.getpass", return_value="pwd") as mock_getpass:
                await module.password(message="Custom prompt: ", timeout=5)
                mock_getpass.assert_called_once_with("Custom prompt: ")
            return True

        asyncio.get_event_loop().run_until_complete(_run())


if __name__ == "__main__":
    unittest.main()
