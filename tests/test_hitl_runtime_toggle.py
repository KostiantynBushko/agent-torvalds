"""
Unit tests for HITLRuntimeToggle.

Tests runtime toggle state management, command parsing, environment variable
monitoring, history tracking, and statistics for the HITL Runtime Toggle component.
"""
import unittest
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.hitl_runtime_toggle import HITLRuntimeToggle, HITL_COMMANDS


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def run(coro):
    """Run a coroutine on a fresh event loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.run_until_complete(asyncio.sleep(0))
        loop.close()


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------

class TestHITLRuntimeToggleInit(unittest.TestCase):
    """Test HITLRuntimeToggle initialisation."""

    def test_default_initial_state(self):
        toggle = HITLRuntimeToggle()
        self.assertTrue(toggle.is_enabled)
        self.assertEqual(toggle.toggle_count, 0)

    def test_custom_initial_state(self):
        toggle = HITLRuntimeToggle(initial_state=False)
        self.assertFalse(toggle.is_enabled)

    def test_custom_env_var(self):
        toggle = HITLRuntimeToggle(env_var="MY_HITL_VAR")
        self.assertEqual(toggle._env_var, "MY_HITL_VAR")

    def test_last_toggled_by_init(self):
        toggle = HITLRuntimeToggle()
        self.assertEqual(toggle._last_toggled_by, "init")

    def test_repr(self):
        toggle = HITLRuntimeToggle(initial_state=True)
        self.assertIn("enabled=True", repr(toggle))
        self.assertIn("toggle_count=0", repr(toggle))

    def test_history_empty_on_init(self):
        toggle = HITLRuntimeToggle()
        self.assertEqual(len(toggle.get_toggle_history()), 0)


class TestToggleAsync(unittest.TestCase):
    """Test async toggle operations."""

    def test_toggle_flips_state_from_enabled(self):
        async def _():
            toggle = HITLRuntimeToggle(initial_state=True)
            new_state = await toggle.toggle(source="user")
            return new_state

        new_state = run(_())
        self.assertFalse(new_state)

    def test_toggle_flips_state_from_disabled(self):
        async def _():
            toggle = HITLRuntimeToggle(initial_state=False)
            new_state = await toggle.toggle(source="user")
            return new_state

        new_state = run(_())
        self.assertTrue(new_state)

    def test_toggle_increments_count(self):
        async def _():
            toggle = HITLRuntimeToggle()
            await toggle.toggle()
            await toggle.toggle()
            return toggle.toggle_count

        count = run(_())
        self.assertEqual(count, 2)

    def test_toggle_records_history(self):
        async def _():
            toggle = HITLRuntimeToggle()
            await toggle.toggle(source="test")
            return toggle.get_toggle_history()

        history = run(_())
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["source"], "test")
        self.assertEqual(history[0]["action"], "toggle")
        self.assertIn("timestamp", history[0])

    def test_multiple_toggles_record_history(self):
        async def _():
            toggle = HITLRuntimeToggle()
            await toggle.toggle(source="user")
            await toggle.toggle(source="api")
            return toggle.get_toggle_history()

        history = run(_())
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["source"], "user")
        self.assertEqual(history[1]["source"], "api")


class TestSetStateAsync(unittest.TestCase):
    """Test async set_state operations."""

    def test_set_enabled_true(self):
        async def _():
            toggle = HITLRuntimeToggle(initial_state=False)
            await toggle.set_state(True, source="user")
            return toggle.is_enabled

        enabled = run(_())
        self.assertTrue(enabled)

    def test_set_enabled_false(self):
        async def _():
            toggle = HITLRuntimeToggle(initial_state=True)
            await toggle.set_state(False, source="user")
            return toggle.is_enabled

        enabled = run(_())
        self.assertFalse(enabled)

    def test_set_same_state_no_change(self):
        async def _():
            toggle = HITLRuntimeToggle(initial_state=True)
            await toggle.set_state(True, source="user")
            return toggle.toggle_count

        count = run(_())
        self.assertEqual(count, 0)

    def test_set_state_records_history(self):
        async def _():
            toggle = HITLRuntimeToggle(initial_state=False)
            await toggle.set_state(True, source="env")
            return toggle.get_toggle_history()

        history = run(_())
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["action"], "set")
        self.assertEqual(history[0]["source"], "env")
        self.assertTrue(history[0]["new_state"])


class TestStatusAsync(unittest.TestCase):
    """Test async status operations."""

    def test_status_returns_dict(self):
        async def _():
            toggle = HITLRuntimeToggle()
            return await toggle.status()

        status = run(_())
        self.assertIsInstance(status, dict)
        self.assertIn("enabled", status)
        self.assertIn("toggle_count", status)
        self.assertIn("last_toggled_by", status)
        self.assertIn("last_toggle_time", status)

    def test_status_values(self):
        async def _():
            toggle = HITLRuntimeToggle(initial_state=True)
            await toggle.toggle(source="test")
            return await toggle.status()

        status = run(_())
        self.assertFalse(status["enabled"])
        self.assertEqual(status["toggle_count"], 1)
        self.assertEqual(status["last_toggled_by"], "test")
        self.assertIsNotNone(status["last_toggle_time"])

    def test_status_sync(self):
        toggle = HITLRuntimeToggle(initial_state=False)
        status = toggle.status_sync()
        self.assertFalse(status["enabled"])
        self.assertEqual(status["toggle_count"], 0)

    def test_status_initial_time_none(self):
        async def _():
            toggle = HITLRuntimeToggle()
            return await toggle.status()

        status = run(_())
        self.assertIsNone(status["last_toggle_time"])


class TestCommandParsing(unittest.TestCase):
    """Test command parsing functionality."""

    def test_toggle_command(self):
        async def _():
            toggle = HITLRuntimeToggle(initial_state=True)
            result = await toggle.process_command("toggle-hitl")
            return result, toggle.is_enabled

        result, enabled = run(_())
        self.assertIsNotNone(result)
        self.assertFalse(enabled)

    def test_status_command(self):
        async def _():
            toggle = HITLRuntimeToggle()
            result = await toggle.process_command("hitl-status")
            return result

        result = run(_())
        self.assertIsNotNone(result)
        self.assertIn("HITL Status", result)
        self.assertIn("ENABLED", result)

    def test_on_command(self):
        async def _():
            toggle = HITLRuntimeToggle(initial_state=False)
            result = await toggle.process_command("hitl-on")
            return result, toggle.is_enabled

        result, enabled = run(_())
        self.assertEqual(result, "HITL enabled")
        self.assertTrue(enabled)

    def test_off_command(self):
        async def _():
            toggle = HITLRuntimeToggle(initial_state=True)
            result = await toggle.process_command("hitl-off")
            return result, toggle.is_enabled

        result, enabled = run(_())
        self.assertEqual(result, "HITL disabled")
        self.assertFalse(enabled)

    def test_help_command(self):
        async def _():
            toggle = HITLRuntimeToggle()
            result = await toggle.process_command("hitl-help")
            return result

        result = run(_())
        self.assertIsNotNone(result)
        self.assertIn("toggle-hitl", result)
        self.assertIn("hitl-status", result)
        self.assertIn("hitl-on", result)
        self.assertIn("hitl-off", result)

    def test_unknown_command(self):
        async def _():
            toggle = HITLRuntimeToggle()
            result = await toggle.process_command("unknown-command")
            return result

        result = run(_())
        self.assertIsNone(result)

    def test_command_case_insensitive(self):
        async def _():
            toggle = HITLRuntimeToggle(initial_state=True)
            result = await toggle.process_command("TOGGLE-HITL")
            return result, toggle.is_enabled

        result, enabled = run(_())
        self.assertIsNotNone(result)
        self.assertFalse(enabled)

    def test_is_hitl_command(self):
        toggle = HITLRuntimeToggle()
        self.assertTrue(toggle.is_hitl_command("toggle-hitl"))
        self.assertTrue(toggle.is_hitl_command("hitl-status"))
        self.assertFalse(toggle.is_hitl_command("random-text"))
        self.assertFalse(toggle.is_hitl_command(""))

    def test_hitl_commands_constant(self):
        self.assertIn("toggle-hitl", HITL_COMMANDS)
        self.assertIn("hitl-status", HITL_COMMANDS)
        self.assertIn("hitl-on", HITL_COMMANDS)
        self.assertIn("hitl-off", HITL_COMMANDS)
        self.assertIn("hitl-help", HITL_COMMANDS)


class TestEnvVarMonitoring(unittest.TestCase):
    """Test environment variable monitoring."""

    def test_check_env_var_enabled(self):
        async def _():
            toggle = HITLRuntimeToggle(initial_state=False, env_var="TEST_HITL")
            os.environ["TEST_HITL"] = "true"
            changed = await toggle.check_env_var()
            return changed, toggle.is_enabled

        changed, enabled = run(_())
        self.assertTrue(changed)
        self.assertTrue(enabled)
        del os.environ["TEST_HITL"]

    def test_check_env_var_disabled(self):
        async def _():
            toggle = HITLRuntimeToggle(initial_state=True, env_var="TEST_HITL2")
            os.environ["TEST_HITL2"] = "false"
            changed = await toggle.check_env_var()
            return changed, toggle.is_enabled

        changed, enabled = run(_())
        self.assertTrue(changed)
        self.assertFalse(enabled)
        del os.environ["TEST_HITL2"]

    def test_check_env_var_1(self):
        async def _():
            toggle = HITLRuntimeToggle(initial_state=False, env_var="TEST_HITL3")
            os.environ["TEST_HITL3"] = "1"
            changed = await toggle.check_env_var()
            return changed, toggle.is_enabled

        changed, enabled = run(_())
        self.assertTrue(changed)
        self.assertTrue(enabled)
        del os.environ["TEST_HITL3"]

    def test_check_env_var_no_change(self):
        async def _():
            toggle = HITLRuntimeToggle(initial_state=True, env_var="TEST_HITL4")
            os.environ["TEST_HITL4"] = "true"
            changed = await toggle.check_env_var()
            return changed

        changed = run(_())
        self.assertFalse(changed)
        del os.environ["TEST_HITL4"]

    def test_check_env_var_empty(self):
        async def _():
            toggle = HITLRuntimeToggle(initial_state=True, env_var="NONEXISTENT_VAR")
            changed = await toggle.check_env_var()
            return changed

        changed = run(_())
        self.assertFalse(changed)

    def test_check_env_var_records_source(self):
        async def _():
            toggle = HITLRuntimeToggle(initial_state=False, env_var="TEST_HITL5")
            os.environ["TEST_HITL5"] = "yes"
            await toggle.check_env_var()
            return toggle._last_toggled_by

        source = run(_())
        self.assertEqual(source, "env")
        del os.environ["TEST_HITL5"]


class TestStats(unittest.TestCase):
    """Test statistics functionality."""

    def test_empty_stats(self):
        toggle = HITLRuntimeToggle(initial_state=True)
        stats = toggle.get_stats()
        self.assertEqual(stats["current_state"], True)
        self.assertEqual(stats["total_toggles"], 0)
        self.assertEqual(stats["sources"], set())
        self.assertIsNone(stats["first_toggle"])
        self.assertIsNone(stats["last_toggle"])

    def test_stats_after_toggles(self):
        async def _():
            toggle = HITLRuntimeToggle()
            await toggle.toggle(source="user")
            await toggle.toggle(source="api")
            return toggle.get_stats()

        stats = run(_())
        self.assertEqual(stats["total_toggles"], 2)
        self.assertIn("user", stats["sources"])
        self.assertIn("api", stats["sources"])
        self.assertIsNotNone(stats["first_toggle"])
        self.assertIsNotNone(stats["last_toggle"])

    def test_stats_sources_unique(self):
        async def _():
            toggle = HITLRuntimeToggle()
            await toggle.toggle(source="user")
            await toggle.toggle(source="user")
            await toggle.toggle(source="api")
            return toggle.get_stats()

        stats = run(_())
        self.assertEqual(len(stats["sources"]), 2)


class TestReset(unittest.TestCase):
    """Test reset functionality."""

    def test_reset_clears_history(self):
        async def _():
            toggle = HITLRuntimeToggle()
            await toggle.toggle()
            self.assertEqual(len(toggle.get_toggle_history()), 1)
            toggle.reset()
            return len(toggle.get_toggle_history())

        count = run(_())
        self.assertEqual(count, 0)

    def test_reset_preserves_state(self):
        async def _():
            toggle = HITLRuntimeToggle(initial_state=True)
            await toggle.toggle()
            toggle.reset()
            return toggle.is_enabled

        enabled = run(_())
        self.assertFalse(enabled)


class TestIntegration(unittest.TestCase):
    """Integration tests for multiple operations."""

    def test_full_workflow(self):
        async def _():
            toggle = HITLRuntimeToggle(initial_state=True)

            # Initial state
            self.assertTrue(toggle.is_enabled)
            self.assertEqual(toggle.toggle_count, 0)

            # Toggle off
            await toggle.toggle(source="user")
            self.assertFalse(toggle.is_enabled)
            self.assertEqual(toggle.toggle_count, 1)

            # Toggle on
            await toggle.toggle(source="interactive")
            self.assertTrue(toggle.is_enabled)
            self.assertEqual(toggle.toggle_count, 2)

            # Set off explicitly
            await toggle.set_state(False, source="api")
            self.assertFalse(toggle.is_enabled)
            self.assertEqual(toggle.toggle_count, 3)

            # Set off again (no change)
            await toggle.set_state(False, source="api")
            self.assertEqual(toggle.toggle_count, 3)

            # Check status
            status = await toggle.status()
            self.assertFalse(status["enabled"])
            self.assertEqual(status["toggle_count"], 3)
            self.assertEqual(status["last_toggled_by"], "api")

            return True

        result = run(_())
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
