"""
Unit tests for WhiptailInputModule.

Tests the async whiptail-based input methods with mocked whiptail dialogs:
- is_available(): availability checking
- prompt(): text input via dialog with timeout
- confirm(): yes/no confirmation via dialog
- menu(): option selection via dialog
- timeout handling for all methods
- fallback when whiptail is unavailable
- error handling

Uses unittest.mock to avoid actually spawning whiptail dialogs during tests.
"""
import unittest
import asyncio
import sys
import os
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.whiptail_input_module import WhiptailInputModule


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_async(coro):
    """Run an async coroutine in a fresh event loop for unit tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Constructor / availability
# ---------------------------------------------------------------------------

class TestWhiptailInputModuleInit(unittest.TestCase):
    """Test WhiptailInputModule initialization and availability."""

    def test_default_params(self):
        module = WhiptailInputModule()
        self.assertEqual(module.title, "Agent Question")
        self.assertEqual(module.backtitle, "AI Agent requires your input")
        self.assertEqual(module.height, 10)
        self.assertEqual(module.width, 60)

    def test_custom_params(self):
        module = WhiptailInputModule(
            title="Custom Title",
            backtitle="Custom Backtitle",
            height=20,
            width=80,
        )
        self.assertEqual(module.title, "Custom Title")
        self.assertEqual(module.backtitle, "Custom Backtitle")
        self.assertEqual(module.height, 20)
        self.assertEqual(module.width, 80)

    def test_is_available_true(self):
        with patch(
            "components.whiptail_password.WhiptailPasswordPrompter.is_available",
            return_value={"available": True, "binary_path": "/usr/bin/whiptail"},
        ):
            self.assertTrue(WhiptailInputModule.is_available())

    def test_is_available_false(self):
        with patch(
            "components.whiptail_password.WhiptailPasswordPrompter.is_available",
            return_value={"available": False},
        ):
            self.assertFalse(WhiptailInputModule.is_available())


# ---------------------------------------------------------------------------
# prompt()
# ---------------------------------------------------------------------------

class TestWhiptailPrompt(unittest.TestCase):
    """Test the prompt() method."""

    def _mock_whiptail_prompt(self, return_value="hello"):
        """Helper to mock the whiptail Whiptail class."""
        mock_wt = MagicMock()
        mock_wt.prompt.return_value = return_value
        return mock_wt

    def test_prompt_returns_user_input(self):
        async def _run():
            mock_wt = self._mock_whiptail_prompt("hello world")
            with patch("components.whiptail_input_module.WhiptailInputModule.is_available", return_value=True):
                with patch("whiptail.Whiptail", return_value=mock_wt):
                    module = WhiptailInputModule()
                    result = await module.prompt("Enter name:", default="anon", timeout=5)
            return result

        result = _run_async(_run())
        self.assertEqual(result, "hello world")

    def test_prompt_returns_default_on_empty(self):
        async def _run():
            mock_wt = self._mock_whiptail_prompt("  ")
            with patch("components.whiptail_input_module.WhiptailInputModule.is_available", return_value=True):
                with patch("whiptail.Whiptail", return_value=mock_wt):
                    module = WhiptailInputModule()
                    result = await module.prompt("Enter:", default="fallback", timeout=5)
            return result

        result = _run_async(_run())
        self.assertEqual(result, "fallback")

    def test_prompt_returns_default_when_unavailable(self):
        async def _run():
            with patch("components.whiptail_input_module.WhiptailInputModule.is_available", return_value=False):
                module = WhiptailInputModule()
                result = await module.prompt("Enter:", default="fallback", timeout=5)
            return result

        result = _run_async(_run())
        self.assertEqual(result, "fallback")

    def test_prompt_timeout_returns_default(self):
        async def _run():
            mock_wt = MagicMock()
            mock_wt.prompt.side_effect = lambda **kw: asyncio.sleep(10)
            with patch("components.whiptail_input_module.WhiptailInputModule.is_available", return_value=True):
                with patch("whiptail.Whiptail", return_value=mock_wt):
                    module = WhiptailInputModule()
                    result = await module.prompt("Enter:", default="timed_out", timeout=1)
            return result

        result = _run_async(_run())
        self.assertEqual(result, "timed_out")

    def test_prompt_exception_returns_default(self):
        async def _run():
            mock_wt = MagicMock()
            mock_wt.prompt.side_effect = RuntimeError("dialog crashed")
            with patch("components.whiptail_input_module.WhiptailInputModule.is_available", return_value=True):
                with patch("whiptail.Whiptail", return_value=mock_wt):
                    module = WhiptailInputModule()
                    result = await module.prompt("Enter:", default="err_val", timeout=5)
            return result

        result = _run_async(_run())
        self.assertEqual(result, "err_val")

    def test_prompt_uses_custom_title(self):
        async def _run():
            mock_wt = self._mock_whiptail_prompt("test")
            with patch("components.whiptail_input_module.WhiptailInputModule.is_available", return_value=True):
                with patch("whiptail.Whiptail", return_value=mock_wt) as wt_cls:
                    module = WhiptailInputModule()
                    await module.prompt("Enter:", title="My Title", timeout=5)
                    # Check Whiptail was called with the custom title
                    wt_cls.assert_called_once()
                    call_kwargs = wt_cls.call_args[1]
                    self.assertEqual(call_kwargs["title"], "My Title")
            return True

        _run_async(_run())


# ---------------------------------------------------------------------------
# confirm()
# ---------------------------------------------------------------------------

class TestWhiptailConfirm(unittest.TestCase):
    """Test the confirm() method."""

    def _mock_whiptail_result(self, returncode=0):
        """Helper to create a mock whiptail result object."""
        mock_result = MagicMock()
        mock_result.returncode = returncode
        return mock_result

    def test_confirm_yes(self):
        async def _run():
            mock_wt = MagicMock()
            mock_wt.run.return_value = self._mock_whiptail_result(returncode=0)
            with patch("components.whiptail_input_module.WhiptailInputModule.is_available", return_value=True):
                with patch("whiptail.Whiptail", return_value=mock_wt):
                    module = WhiptailInputModule()
                    result = await module.confirm("Proceed?", default_yes=True, timeout=5)
            return result

        result = _run_async(_run())
        self.assertTrue(result)

    def test_confirm_no(self):
        async def _run():
            mock_wt = MagicMock()
            mock_wt.run.return_value = self._mock_whiptail_result(returncode=1)
            with patch("components.whiptail_input_module.WhiptailInputModule.is_available", return_value=True):
                with patch("whiptail.Whiptail", return_value=mock_wt):
                    module = WhiptailInputModule()
                    result = await module.confirm("Proceed?", default_yes=True, timeout=5)
            return result

        result = _run_async(_run())
        self.assertFalse(result)

    def test_confirm_default_yes_on_unavailable(self):
        async def _run():
            with patch("components.whiptail_input_module.WhiptailInputModule.is_available", return_value=False):
                module = WhiptailInputModule()
                result = await module.confirm("Proceed?", default_yes=True, timeout=5)
            return result

        result = _run_async(_run())
        self.assertTrue(result)

    def test_confirm_default_no_on_unavailable(self):
        async def _run():
            with patch("components.whiptail_input_module.WhiptailInputModule.is_available", return_value=False):
                module = WhiptailInputModule()
                result = await module.confirm("Proceed?", default_yes=False, timeout=5)
            return result

        result = _run_async(_run())
        self.assertFalse(result)

    def test_confirm_timeout_returns_default(self):
        async def _run():
            mock_wt = MagicMock()
            mock_wt.run.side_effect = lambda **kw: asyncio.sleep(10)
            with patch("components.whiptail_input_module.WhiptailInputModule.is_available", return_value=True):
                with patch("whiptail.Whiptail", return_value=mock_wt):
                    module = WhiptailInputModule()
                    result = await module.confirm("Proceed?", default_yes=True, timeout=1)
            return result

        result = _run_async(_run())
        self.assertTrue(result)

    def test_confirm_exception_returns_default(self):
        async def _run():
            mock_wt = MagicMock()
            mock_wt.run.side_effect = RuntimeError("crash")
            with patch("components.whiptail_input_module.WhiptailInputModule.is_available", return_value=True):
                with patch("whiptail.Whiptail", return_value=mock_wt):
                    module = WhiptailInputModule()
                    result = await module.confirm("Proceed?", default_yes=True, timeout=5)
            return result

        result = _run_async(_run())
        self.assertTrue(result)

    def test_confirm_defaultno_flag(self):
        async def _run():
            mock_wt = MagicMock()
            mock_wt.run.return_value = self._mock_whiptail_result(returncode=0)
            with patch("components.whiptail_input_module.WhiptailInputModule.is_available", return_value=True):
                with patch("whiptail.Whiptail", return_value=mock_wt):
                    module = WhiptailInputModule()
                    await module.confirm("Proceed?", default_yes=False, timeout=5)
                    # Check that --defaultno was passed
                    mock_wt.run.assert_called_once()
                    call_kwargs = mock_wt.run.call_args[1]
                    self.assertIn("--defaultno", call_kwargs["extra"])
            return True

        _run_async(_run())


# ---------------------------------------------------------------------------
# menu()
# ---------------------------------------------------------------------------

class TestWhiptailMenu(unittest.TestCase):
    """Test the menu() method."""

    def test_menu_selects_first_option(self):
        async def _run():
            mock_wt = MagicMock()
            mock_wt.menu.return_value = "1"
            with patch("components.whiptail_input_module.WhiptailInputModule.is_available", return_value=True):
                with patch("whiptail.Whiptail", return_value=mock_wt):
                    module = WhiptailInputModule()
                    result = await module.menu("Choose:", ["opt_a", "opt_b", "opt_c"], timeout=5)
            return result

        result = _run_async(_run())
        self.assertEqual(result, "opt_a")

    def test_menu_selects_second_option(self):
        async def _run():
            mock_wt = MagicMock()
            mock_wt.menu.return_value = "2"
            with patch("components.whiptail_input_module.WhiptailInputModule.is_available", return_value=True):
                with patch("whiptail.Whiptail", return_value=mock_wt):
                    module = WhiptailInputModule()
                    result = await module.menu("Choose:", ["opt_a", "opt_b", "opt_c"], timeout=5)
            return result

        result = _run_async(_run())
        self.assertEqual(result, "opt_b")

    def test_menu_selects_third_option(self):
        async def _run():
            mock_wt = MagicMock()
            mock_wt.menu.return_value = "3"
            with patch("components.whiptail_input_module.WhiptailInputModule.is_available", return_value=True):
                with patch("whiptail.Whiptail", return_value=mock_wt):
                    module = WhiptailInputModule()
                    result = await module.menu("Choose:", ["opt_a", "opt_b", "opt_c"], timeout=5)
            return result

        result = _run_async(_run())
        self.assertEqual(result, "opt_c")

    def test_menu_invalid_tag_returns_first(self):
        async def _run():
            mock_wt = MagicMock()
            mock_wt.menu.return_value = "abc"
            with patch("components.whiptail_input_module.WhiptailInputModule.is_available", return_value=True):
                with patch("whiptail.Whiptail", return_value=mock_wt):
                    module = WhiptailInputModule()
                    result = await module.menu("Choose:", ["opt_a", "opt_b"], timeout=5)
            return result

        result = _run_async(_run())
        self.assertEqual(result, "opt_a")

    def test_menu_out_of_range_returns_first(self):
        async def _run():
            mock_wt = MagicMock()
            mock_wt.menu.return_value = "99"
            with patch("components.whiptail_input_module.WhiptailInputModule.is_available", return_value=True):
                with patch("whiptail.Whiptail", return_value=mock_wt):
                    module = WhiptailInputModule()
                    result = await module.menu("Choose:", ["opt_a", "opt_b"], timeout=5)
            return result

        result = _run_async(_run())
        self.assertEqual(result, "opt_a")

    def test_menu_unavailable_returns_first(self):
        async def _run():
            with patch("components.whiptail_input_module.WhiptailInputModule.is_available", return_value=False):
                module = WhiptailInputModule()
                result = await module.menu("Choose:", ["opt_a", "opt_b"], timeout=5)
            return result

        result = _run_async(_run())
        self.assertEqual(result, "opt_a")

    def test_menu_empty_options_returns_empty(self):
        async def _run():
            with patch("components.whiptail_input_module.WhiptailInputModule.is_available", return_value=False):
                module = WhiptailInputModule()
                result = await module.menu("Choose:", [], timeout=5)
            return result

        result = _run_async(_run())
        self.assertEqual(result, "")

    def test_menu_timeout_returns_first(self):
        async def _run():
            mock_wt = MagicMock()
            mock_wt.menu.side_effect = lambda **kw: asyncio.sleep(10)
            with patch("components.whiptail_input_module.WhiptailInputModule.is_available", return_value=True):
                with patch("whiptail.Whiptail", return_value=mock_wt):
                    module = WhiptailInputModule()
                    result = await module.menu("Choose:", ["opt_a", "opt_b"], timeout=1)
            return result

        result = _run_async(_run())
        self.assertEqual(result, "opt_a")

    def test_menu_exception_returns_first(self):
        async def _run():
            mock_wt = MagicMock()
            mock_wt.menu.side_effect = RuntimeError("crash")
            with patch("components.whiptail_input_module.WhiptailInputModule.is_available", return_value=True):
                with patch("whiptail.Whiptail", return_value=mock_wt):
                    module = WhiptailInputModule()
                    result = await module.menu("Choose:", ["opt_a", "opt_b"], timeout=5)
            return result

        result = _run_async(_run())
        self.assertEqual(result, "opt_a")

    def test_menu_formats_items_correctly(self):
        """Verify that items are passed as (tag, description) tuples."""
        async def _run():
            mock_wt = MagicMock()
            mock_wt.menu.return_value = "1"
            with patch("components.whiptail_input_module.WhiptailInputModule.is_available", return_value=True):
                with patch("whiptail.Whiptail", return_value=mock_wt):
                    module = WhiptailInputModule()
                    await module.menu("Choose:", ["Option A", "Option B"], timeout=5)
                    # Check that menu was called with properly formatted items
                    mock_wt.menu.assert_called_once()
                    call_kwargs = mock_wt.menu.call_args[1]
                    items = call_kwargs["items"]
                    self.assertEqual(len(items), 2)
                    self.assertEqual(items[0], ("1", "Option A"))
                    self.assertEqual(items[1], ("2", "Option B"))
            return True

        _run_async(_run())


# ---------------------------------------------------------------------------
# Run tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
