"""
Tests for the agent-cache zero-stats fix.

Covers the three fixes described in
``investigate/agent-cache-zero-stats/investigation_agent_cache_zero_stats.md``:

* **Fix A** — the LLM's own ``callback_manager`` is the one LlamaIndex
  actually uses, so it must carry the per-request stats handler.
  ``FunctionAgent(callback_manager=...)`` / ``agent.run(callback_manager=...)``
  are silently dropped by pydantic.
* **Fix B** — ``CBEventType.FUNCTION_CALL`` is never emitted by llama-index
  0.14.x, so tool calls are sourced from the workflow event stream and fed
  into the handler by the ``EventConsumer``.
* **Fix C** — ``save_request_stats`` must not persist ``None`` where a
  number is expected, and ``get_stats_summary`` must tolerate such entries.

No network access is required (uses ``MockFunctionCallingLLM``).
"""
import asyncio
import os
import sys
import unittest
from typing import Any, List

sys.path.insert(0, '.')

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.callbacks import CallbackManager
from llama_index.core.callbacks.schema import CBEventType, EventPayload
from llama_index.core.llms.mock import MockFunctionCallingLLM
from llama_index.core.tools import FunctionTool
from rich.console import Console

from agent_cache_system import get_stats_summary, save_request_stats
from components.event_consumer import EventConsumer
from components.state_handler import StateHandler
from components.stats_handler import (
    RequestStatsHandler,
    _extract_usage,
    bind_callback_manager,
)
from components.spinner_controller import SpinnerController


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _add_two(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


def _make_tool() -> FunctionTool:
    return FunctionTool.from_defaults(fn=_add_two)


class _FakeSpinner(SpinnerController):
    """Spinner that does not animate — keeps test output clean."""

    def start(self) -> None:  # pragma: no cover - trivial
        pass

    def stop(self) -> None:  # pragma: no cover - trivial
        pass

    def pause(self) -> None:  # pragma: no cover - trivial
        pass

    def resume(self) -> None:  # pragma: no cover - trivial
        pass


# ---------------------------------------------------------------------------
# Fix A — LLM callback manager wiring
# ---------------------------------------------------------------------------

class TestCallbackManagerBinding(unittest.TestCase):
    """Fix A: the callback manager must be attached to the LLM instance."""

    def test_bind_sets_manager_on_llm(self):
        agent = FunctionAgent(tools=[], llm=MockFunctionCallingLLM())
        cm = CallbackManager([])
        self.assertTrue(bind_callback_manager(agent, cm))
        self.assertIs(agent.llm.callback_manager, cm)

    def test_bind_returns_false_without_manager(self):
        agent = FunctionAgent(tools=[], llm=MockFunctionCallingLLM())
        self.assertFalse(bind_callback_manager(agent, None))

    def test_bind_returns_false_without_llm(self):
        class _NoLLM:
            llm = None

        self.assertFalse(bind_callback_manager(_NoLLM(), CallbackManager([])))

    def test_function_agent_drops_callback_manager(self):
        """Regression guard: FunctionAgent has no callback_manager field.

        This is the root cause of the zeroed stats — pydantic silently
        ignores the unknown keyword argument.
        """
        agent = FunctionAgent(
            tools=[], llm=MockFunctionCallingLLM(), callback_manager=CallbackManager([])
        )
        self.assertFalse(hasattr(agent, "callback_manager"))

    def test_llm_receives_llm_events_when_bound(self):
        """With the manager bound to the LLM, LLM events reach the handler."""
        stats = RequestStatsHandler(request_id="bind", user_query="q")
        cm = CallbackManager([stats])
        llm = MockFunctionCallingLLM()
        agent = FunctionAgent(tools=[], llm=llm)
        bind_callback_manager(agent, cm)

        async def _run():
            handler = agent.run("hello")
            await handler

        asyncio.run(_run())
        self.assertGreaterEqual(stats.stats.llm_call_count, 1)

    def test_llm_receives_no_events_when_unbound(self):
        """Without the fix the handler sees nothing (the original bug)."""
        stats = RequestStatsHandler(request_id="unbound", user_query="q")
        agent = FunctionAgent(
            tools=[], llm=MockFunctionCallingLLM(), callback_manager=CallbackManager([stats])
        )

        async def _run():
            handler = agent.run("hello")
            await handler

        asyncio.run(_run())
        self.assertEqual(stats.stats.llm_call_count, 0)


# ---------------------------------------------------------------------------
# Fix B — tool calls sourced from the workflow event stream
# ---------------------------------------------------------------------------

class TestToolCallRecording(unittest.TestCase):
    """Fix B: tool calls must be recorded from workflow events."""

    def test_begin_and_end_tool_call(self):
        stats = RequestStatsHandler(request_id="tc", user_query="q")
        stats.begin_tool_call("add_two")
        stats.end_tool_call("add_two")

        self.assertEqual(len(stats.stats.tool_calls), 1)
        record = stats.stats.tool_calls[0]
        self.assertEqual(record.tool_name, "add_two")
        self.assertTrue(record.succeeded)
        self.assertGreaterEqual(record.duration_ms, 0.0)
        self.assertEqual(stats.stats.tools_used, ["add_two"])

    def test_end_without_begin_still_counts(self):
        stats = RequestStatsHandler(request_id="tc2", user_query="q")
        stats.end_tool_call("orphan_tool")
        self.assertEqual(len(stats.stats.tool_calls), 1)

    def test_failed_tool_call_records_error(self):
        stats = RequestStatsHandler(request_id="tc3", user_query="q")
        stats.begin_tool_call("boom")
        stats.end_tool_call("boom", succeeded=False, error_message="kaboom")

        self.assertEqual(len(stats.stats.tool_calls), 1)
        self.assertFalse(stats.stats.tool_calls[0].succeeded)
        self.assertTrue(any("boom" in e for e in stats.stats.errors))

    def test_record_tool_call_one_shot(self):
        stats = RequestStatsHandler(request_id="tc4", user_query="q")
        stats.record_tool_call("add_two", duration_ms=12.5)

        self.assertEqual(len(stats.stats.tool_calls), 1)
        self.assertAlmostEqual(stats.stats.tool_calls[0].duration_ms, 12.5, places=3)

    def test_event_consumer_feeds_stats_handler(self):
        """The EventConsumer forwards workflow tool events to the handler."""
        stats = RequestStatsHandler(request_id="ec", user_query="q")
        consumer = EventConsumer(
            spinner_controller=_FakeSpinner(Console()),
            state_handler=StateHandler(),
            console=Console(),
            stats_handler=stats,
        )

        from llama_index.core.agent.workflow import ToolCall, ToolCallResult
        from llama_index.core.tools import ToolOutput

        asyncio.run(consumer._on_tool_call(ToolCall(tool_name="add_two", tool_kwargs={}, tool_id="t1")))
        asyncio.run(
            consumer._on_tool_call_result(
                ToolCallResult(
                    tool_name="add_two",
                    tool_kwargs={},
                    tool_id="t1",
                    tool_output=ToolOutput(content="3", tool_name="add_two", raw_input={}, raw_output="3"),
                    return_direct=False,
                )
            )
        )

        self.assertEqual(len(stats.stats.tool_calls), 1)
        self.assertEqual(stats.stats.tool_calls[0].tool_name, "add_two")

    def test_set_stats_handler_replaces_previous(self):
        consumer = EventConsumer(
            spinner_controller=_FakeSpinner(Console()),
            state_handler=StateHandler(),
            console=Console(),
        )
        first = RequestStatsHandler(request_id="1", user_query="a")
        second = RequestStatsHandler(request_id="2", user_query="b")
        consumer.set_stats_handler(first)
        self.assertIs(consumer.stats_handler, first)
        consumer.set_stats_handler(second)
        self.assertIs(consumer.stats_handler, second)

    def test_tool_calls_counted_end_to_end(self):
        """Full loop: agent + event consumer + stats handler."""
        stats = RequestStatsHandler(request_id="e2e", user_query="add 1 and 2")
        cm = CallbackManager([stats])
        llm = MockFunctionCallingLLM()
        agent = FunctionAgent(tools=[_make_tool()], llm=llm, max_iterations=3)
        bind_callback_manager(agent, cm)

        consumer = EventConsumer(
            spinner_controller=_FakeSpinner(Console()),
            state_handler=StateHandler(),
            console=Console(),
            stats_handler=stats,
        )

        async def _run():
            handler = agent.run("add 1 and 2")
            await consumer.consume_events(handler, "add 1 and 2")

        asyncio.run(_run())

        self.assertGreaterEqual(stats.stats.llm_call_count, 1)
        self.assertGreaterEqual(len(stats.stats.tool_calls), 1)
        self.assertTrue(
            any(name.lstrip("_") == "add_two" for name in stats.stats.tools_used),
            f"expected add_two in {stats.stats.tools_used}",
        )


    def test_concurrent_calls_to_same_tool_are_paired_correctly(self):
        """The workflow runs tool calls CONCURRENTLY.

        Two calls to the same tool can therefore be in flight at the same
        time. Keying the pending starts by tool name alone would collapse
        them into one entry and mis-pair the timings. The tool_id keeps them
        apart, and each start is matched with its own end.
        """
        stats = RequestStatsHandler(request_id="par", user_query="q")

        stats.begin_tool_call("add_two", tool_id="t1")
        stats.begin_tool_call("add_two", tool_id="t2")

        # Both calls are outstanding — neither start may be lost.
        self.assertEqual(len(stats.stats.tool_calls), 0)

        stats.end_tool_call("add_two", tool_id="t1")
        stats.end_tool_call("add_two", tool_id="t2")

        self.assertEqual(len(stats.stats.tool_calls), 2)
        self.assertEqual(stats.stats.to_dict()["tool_call_count"], 2)
        self.assertEqual(stats.stats.tools_used, ["add_two"])
        # No start may be left dangling.
        self.assertEqual(stats._pending_tool_starts, {})

    def test_same_tool_without_ids_uses_fifo(self):
        """Without ids the queue still pairs starts with ends in order."""
        stats = RequestStatsHandler(request_id="fifo", user_query="q")

        stats.begin_tool_call("add_two")
        stats.begin_tool_call("add_two")
        stats.end_tool_call("add_two")
        stats.end_tool_call("add_two")

        self.assertEqual(len(stats.stats.tool_calls), 2)
        self.assertEqual(stats._pending_tool_starts, {})

    def test_ends_with_unknown_id_still_counts(self):
        """An end for an unknown id must still count the call."""
        stats = RequestStatsHandler(request_id="unk", user_query="q")
        stats.end_tool_call("add_two", tool_id="never-seen")
        self.assertEqual(len(stats.stats.tool_calls), 1)
        self.assertEqual(stats.stats.to_dict()["tool_call_count"], 1)


# ---------------------------------------------------------------------------
# Fix C — defensive normalisation in the cache layer
# ---------------------------------------------------------------------------

class TestStatsPersistence(unittest.TestCase):
    """Fix C: None must never be persisted, and aggregation must be safe."""

    def test_save_request_stats_normalises_missing_keys(self):
        save_request_stats({"request_id": "abc", "total_duration_ms": 12.5})

        from agent_cache_system import _get_cache
        cache = _get_cache()
        entry = cache["request_stats"][-1]
        for key in (
            "duration_ms", "llm_calls", "total_tokens",
            "prompt_tokens", "completion_tokens",
            "tool_call_count", "error_count",
        ):
            self.assertIsNotNone(entry[key], f"{key} must not be None")
            self.assertIsInstance(entry[key], (int, float))
        self.assertEqual(entry["tools_used"], [])

    def test_save_request_stats_tolerates_none_values(self):
        save_request_stats(
            {
                "request_id": "def",
                "total_duration_ms": None,
                "llm_call_count": None,
                "total_tokens": None,
                "total_prompt_tokens": None,
                "total_completion_tokens": None,
                "tool_call_count": None,
                "error_count": None,
            }
        )
        from agent_cache_system import _get_cache
        entry = _get_cache()["request_stats"][-1]
        self.assertEqual(entry["total_tokens"], 0)
        self.assertEqual(entry["llm_calls"], 0)

    def test_get_stats_summary_survives_none_entries(self):
        save_request_stats({"request_id": "g1", "total_tokens": 10, "llm_call_count": 1})
        save_request_stats({"request_id": "g2", "total_tokens": None, "llm_call_count": None})

        summary = get_stats_summary()
        self.assertNotIn("error", summary, f"summary failed: {summary}")
        self.assertIn("total_requests", summary)

    def test_get_stats_summary_survives_legacy_none_entries(self):
        """A hand-edited / legacy entry with None must not break aggregation."""
        from agent_cache_system import _get_cache, _save_cache
        cache = _get_cache()
        cache.setdefault("request_stats", []).append(
            {
                "request_id": "legacy",
                "duration_ms": None,
                "llm_calls": None,
                "total_tokens": None,
                "prompt_tokens": None,
                "completion_tokens": None,
                "tools_used": None,
                "tool_call_count": None,
                "error_count": None,
            }
        )
        _save_cache(cache)

        summary = get_stats_summary()
        self.assertNotIn("error", summary, f"summary failed: {summary}")


# ---------------------------------------------------------------------------
# Token extraction robustness
# ---------------------------------------------------------------------------

class TestUsageExtraction(unittest.TestCase):
    """The usage extractor must cope with the shapes providers emit."""

    def test_ollama_raw_usage(self):
        class _Resp:
            raw = {"usage": {"prompt_tokens": 10, "completion_tokens": 5}}

        self.assertEqual(
            _extract_usage(_Resp()),
            {"prompt_tokens": 10, "completion_tokens": 5},
        )

    def test_ollama_raw_wire_format(self):
        class _Resp:
            raw = {"prompt_eval_count": 12, "eval_count": 7}

        usage = _extract_usage(_Resp())
        self.assertEqual(usage["prompt_tokens"], 12)
        self.assertEqual(usage["completion_tokens"], 7)

    def test_usage_attribute(self):
        class _Resp:
            usage = {"prompt_tokens": 3, "completion_tokens": 4}
            raw = {}

        self.assertEqual(
            _extract_usage(_Resp()),
            {"prompt_tokens": 3, "completion_tokens": 4},
        )

    def test_additional_kwargs_fallback(self):
        class _Resp:
            raw = {}
            additional_kwargs = {"usage": {"prompt_tokens": 1, "completion_tokens": 2}}

        self.assertEqual(
            _extract_usage(_Resp()),
            {"prompt_tokens": 1, "completion_tokens": 2},
        )

    def test_no_usage_returns_empty(self):
        class _Resp:
            raw = {}

        self.assertEqual(_extract_usage(_Resp()), {})
        self.assertEqual(_extract_usage(None), {})

    def test_tokens_are_counted_in_stats(self):
        stats = RequestStatsHandler(request_id="tok", user_query="q")

        class _Resp:
            raw = {"usage": {"prompt_tokens": 100, "completion_tokens": 50}}

        stats.on_event_end(
            event_type=CBEventType.LLM,
            payload={EventPayload.RESPONSE: _Resp()},
            event_id="e1",
        )
        self.assertEqual(stats.stats.total_prompt_tokens, 100)
        self.assertEqual(stats.stats.total_completion_tokens, 50)
        self.assertEqual(stats.stats.total_tokens, 150)
        self.assertEqual(stats.stats.llm_call_count, 1)


# ---------------------------------------------------------------------------
# Per-request isolation
# ---------------------------------------------------------------------------

class TestPerRequestIsolation(unittest.TestCase):
    """Consecutive requests must not leak stats into each other."""

    def test_each_request_has_its_own_stats(self):
        async def _run():
            llm = MockFunctionCallingLLM()
            agent = FunctionAgent(tools=[], llm=llm)

            results = []
            for _ in range(3):
                stats = RequestStatsHandler(request_id="r", user_query="q")
                cm = CallbackManager([stats])
                bind_callback_manager(agent, cm)
                handler = agent.run("hello")
                await handler
                results.append(stats.finalize())
            return results

        results = asyncio.run(_run())
        for stats in results:
            self.assertGreaterEqual(stats.llm_call_count, 1)
            # Each request must count only its own LLM calls.
            self.assertEqual(stats.llm_call_count, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
