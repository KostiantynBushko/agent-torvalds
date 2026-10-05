"""
Unit tests for TimeoutManager.

Tests timeout handling, fallback answers, logging, retry logic, and
statistics for the HITL TimeoutManager component.
"""
import unittest
import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.timeout_manager import TimeoutManager


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

async def fast_answer(value: str = "ok"):
    """Simulate an instant user response."""
    return value


async def slow_answer(delay: float, value: str = "late"):
    """Simulate a slow user response."""
    await asyncio.sleep(delay)
    return value


async def raising_answer():
    """Simulate a prompt that raises."""
    raise ValueError("boom")


def run(coro):
    """Run a coroutine on a fresh event loop (avoids 'loop closed' issues)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.run_until_complete(asyncio.sleep(0))  # flush pending tasks
        loop.close()


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------

class TestTimeoutManagerInit(unittest.TestCase):
    """Test TimeoutManager initialisation."""

    def test_default_timeout(self):
        mgr = TimeoutManager()
        self.assertEqual(mgr.default_timeout, 30)
        self.assertEqual(len(mgr.get_timeout_log()), 0)

    def test_custom_timeout(self):
        mgr = TimeoutManager(default_timeout=60)
        self.assertEqual(mgr.default_timeout, 60)

    def test_negative_timeout_raises(self):
        with self.assertRaises(ValueError):
            TimeoutManager(default_timeout=-1)

    def test_repr(self):
        mgr = TimeoutManager(default_timeout=15)
        self.assertIn("default_timeout=15", repr(mgr))
        self.assertIn("logged_timeouts=0", repr(mgr))


class TestPromptWithTimeout(unittest.TestCase):
    """Test the prompt_with_timeout() method."""

    def test_fast_answer_returns_value_no_timeout(self):
        async def _():
            mgr = TimeoutManager(default_timeout=5)
            answer, timed_out = await mgr.prompt_with_timeout(fast_answer, timeout=5)
            return answer, timed_out

        answer, timed_out = run(_())
        self.assertEqual(answer, "ok")
        self.assertFalse(timed_out)

    def test_timeout_returns_default_answer(self):
        async def _():
            mgr = TimeoutManager(default_timeout=1)
            answer, timed_out = await mgr.prompt_with_timeout(
                lambda: slow_answer(10),
                timeout=1,
                default_answer="fallback",
                question_id="q1",
            )
            return answer, timed_out

        answer, timed_out = run(_())
        self.assertEqual(answer, "fallback")
        self.assertTrue(timed_out)

    def test_uses_default_timeout_when_none(self):
        async def _():
            mgr = TimeoutManager(default_timeout=2)
            answer, timed_out = await mgr.prompt_with_timeout(
                lambda: slow_answer(5),
                default_answer="dt",
            )
            return answer, timed_out

        answer, timed_out = run(_())
        self.assertEqual(answer, "dt")
        self.assertTrue(timed_out)

    def test_timeout_logs_event(self):
        async def _():
            mgr = TimeoutManager(default_timeout=1)
            await mgr.prompt_with_timeout(
                lambda: slow_answer(10),
                timeout=1,
                default_answer="x",
                question_id="logged-q",
            )
            return mgr.get_timeout_log()

        log = run(_())
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["question_id"], "logged-q")
        self.assertEqual(log[0]["timeout"], 1)
        self.assertEqual(log[0]["default_answer"], "x")
        self.assertIn("timestamp", log[0])

    def test_no_timeout_does_not_log(self):
        async def _():
            mgr = TimeoutManager(default_timeout=5)
            await mgr.prompt_with_timeout(fast_answer, timeout=5)
            return mgr.get_timeout_log()

        log = run(_())
        self.assertEqual(len(log), 0)

    def test_custom_timeout_overrides_default(self):
        async def _():
            mgr = TimeoutManager(default_timeout=60)
            answer, timed_out = await mgr.prompt_with_timeout(
                lambda: slow_answer(2),
                timeout=1,
                default_answer="short",
            )
            return answer, timed_out

        answer, timed_out = run(_())
        self.assertEqual(answer, "short")
        self.assertTrue(timed_out)


class TestPromptWithRetry(unittest.TestCase):
    """Test the prompt_with_retry() method."""

    def test_returns_on_first_success(self):
        async def _():
            mgr = TimeoutManager(default_timeout=5)
            answer, timed_out, attempts = await mgr.prompt_with_retry(
                fast_answer,
                max_retries=3,
            )
            return answer, timed_out, attempts

        answer, timed_out, attempts = run(_())
        self.assertEqual(answer, "ok")
        self.assertFalse(timed_out)
        self.assertEqual(attempts, 1)

    def test_retries_then_succeeds(self):
        """First two attempts time out, third succeeds."""
        call_count = 0

        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                await asyncio.sleep(10)  # will timeout
            return "success"

        async def _():
            mgr = TimeoutManager(default_timeout=1)
            answer, timed_out, attempts = await mgr.prompt_with_retry(
                flaky,
                timeout=1,
                max_retries=3,
                retry_delay=0.01,
            )
            return answer, timed_out, attempts

        answer, timed_out, attempts = run(_())
        self.assertEqual(answer, "success")
        self.assertFalse(timed_out)
        self.assertEqual(attempts, 3)

    def test_all_retries_timeout_returns_default(self):
        async def _():
            mgr = TimeoutManager(default_timeout=1)
            answer, timed_out, attempts = await mgr.prompt_with_retry(
                lambda: slow_answer(10),
                timeout=1,
                default_answer="give_up",
                max_retries=2,
                retry_delay=0.01,
            )
            return answer, timed_out, attempts

        answer, timed_out, attempts = run(_())
        self.assertEqual(answer, "give_up")
        self.assertTrue(timed_out)
        self.assertEqual(attempts, 3)  # 1 initial + 2 retries

    def test_retry_logs_with_attempts(self):
        async def _():
            mgr = TimeoutManager(default_timeout=1)
            await mgr.prompt_with_retry(
                lambda: slow_answer(10),
                timeout=1,
                default_answer="x",
                question_id="retry-q",
                max_retries=1,
                retry_delay=0.01,
            )
            return mgr.get_timeout_log()

        log = run(_())
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["question_id"], "retry-q")
        self.assertIn("attempts", log[0])
        self.assertEqual(log[0]["attempts"], 2)


class TestGetTimeoutLog(unittest.TestCase):
    """Test get_timeout_log() returns a copy."""

    def test_returns_copy(self):
        async def _():
            mgr = TimeoutManager(default_timeout=1)
            await mgr.prompt_with_timeout(
                lambda: slow_answer(10),
                timeout=1,
                default_answer="a",
                question_id="q1",
            )
            log = mgr.get_timeout_log()
            log.append({"fake": True})
            return mgr.get_timeout_log()

        final_log = run(_())
        self.assertEqual(len(final_log), 1)
        self.assertNotIn({"fake": True}, final_log)


class TestReset(unittest.TestCase):
    """Test reset() clears the log."""

    def test_clears_log(self):
        async def _():
            mgr = TimeoutManager(default_timeout=1)
            await mgr.prompt_with_timeout(
                lambda: slow_answer(10),
                timeout=1,
                default_answer="a",
            )
            self.assertEqual(len(mgr.get_timeout_log()), 1)
            mgr.reset()
            return mgr.get_timeout_log()

        log = run(_())
        self.assertEqual(len(log), 0)


class TestGetStats(unittest.TestCase):
    """Test get_stats() summary statistics."""

    def test_empty_stats(self):
        mgr = TimeoutManager()
        stats = mgr.get_stats()
        self.assertEqual(stats["total_timeouts"], 0)
        self.assertEqual(stats["first_timeout"], None)
        self.assertEqual(stats["last_timeout"], None)

    def test_stats_after_timeouts(self):
        async def _():
            mgr = TimeoutManager(default_timeout=1)
            await mgr.prompt_with_timeout(
                lambda: slow_answer(10),
                timeout=1,
                default_answer="a",
                question_id="q1",
            )
            await asyncio.sleep(0.01)
            await mgr.prompt_with_timeout(
                lambda: slow_answer(10),
                timeout=1,
                default_answer="b",
                question_id="q2",
            )
            return mgr.get_stats()

        stats = run(_())
        self.assertEqual(stats["total_timeouts"], 2)
        self.assertIn("q1", stats["question_ids"])
        self.assertIn("q2", stats["question_ids"])
        self.assertIsNotNone(stats["first_timeout"])
        self.assertIsNotNone(stats["last_timeout"])
        self.assertEqual(stats["first_timeout"], stats["last_timeout"].rsplit(".", 1)[0] if stats["first_timeout"] == stats["last_timeout"] else stats["first_timeout"])


class TestTimeoutManagerIntegration(unittest.TestCase):
    """Integration-style tests with multiple prompts."""

    def test_multiple_prompts_log_correctly(self):
        async def _():
            mgr = TimeoutManager(default_timeout=1)

            # Fast — no timeout
            a1, t1 = await mgr.prompt_with_timeout(fast_answer, timeout=2)
            self.assertFalse(t1)

            # Slow — timeout
            a2, t2 = await mgr.prompt_with_timeout(
                lambda: slow_answer(10),
                timeout=1,
                default_answer="fallback",
                question_id="slow-q",
            )
            self.assertTrue(t2)

            # Another fast
            a3, t3 = await mgr.prompt_with_timeout(lambda: fast_answer("bye"), timeout=2)
            self.assertFalse(t3)

            return a1, a2, a3, mgr.get_stats()

        a1, a2, a3, stats = run(_())
        self.assertEqual(a1, "ok")
        self.assertEqual(a2, "fallback")
        self.assertEqual(a3, "bye")
        self.assertEqual(stats["total_timeouts"], 1)


if __name__ == "__main__":
    unittest.main()
