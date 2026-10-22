"""
Regression tests for the "no timeout" HITL convention.

The agent must wait for the user's answer *constantly* — there is no
deadline by default.  A timeout of ``-1`` means "no timeout" and is
translated into the ``None`` that ``asyncio.wait_for`` and
``Context.wait_for_event`` understand as "wait indefinitely".

Why this matters
----------------
The previous default was 30 seconds, and the value was *not* carried
consistently through the HITL chain:

* ``TimeoutManager`` and the input modules passed the raw value to
  ``asyncio.wait_for``, where any value ``<= 0`` expires **immediately**;
* the agent step padded the timeout by 5 seconds
  (``timeout=timeout + 5``), so a hypothetical ``-1`` would have become a
  4 second deadline instead of "no deadline";
* ``HumanLoopHandler`` clamped the value with ``max(1, default_timeout)``,
  which turned ``-1`` into 1 second;
* the TUI counted down from a negative value and showed ``0s``.

These tests pin the whole chain down.

Category: HITL / Tests
Retriever Keywords: hitl, timeout, no timeout, indefinite, wait forever
"""
import asyncio
import os
import sys
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.hitl_timeout import (
    NO_TIMEOUT,
    describe_timeout,
    is_no_timeout,
    normalize_timeout,
    validate_timeout,
)
from components.console_input_module import ConsoleInputModule
from components.event_consumer import EventConsumer
from components.hitl_events import AgentQuestionEvent
from components.human_loop_handler import HumanLoopHandler
from components.timeout_manager import TimeoutManager


# ----------------------------------------------------------------------
# The helper module
# ----------------------------------------------------------------------


class TestHitlTimeoutHelpers(unittest.TestCase):
    """The convention helpers."""

    def test_no_timeout_constant(self):
        self.assertEqual(NO_TIMEOUT, -1)

    def test_is_no_timeout(self):
        self.assertTrue(is_no_timeout(-1))
        self.assertTrue(is_no_timeout(-5))
        self.assertTrue(is_no_timeout(None))
        self.assertFalse(is_no_timeout(0))
        self.assertFalse(is_no_timeout(30))

    def test_normalize_timeout_translates_to_none(self):
        """-1 must become None — that is what asyncio calls "forever"."""
        self.assertIsNone(normalize_timeout(-1))
        self.assertIsNone(normalize_timeout(None))
        self.assertEqual(normalize_timeout(30), 30.0)
        self.assertEqual(normalize_timeout(0), 0.0)

    def test_validate_timeout_allows_minus_one(self):
        self.assertEqual(validate_timeout(-1), -1)
        self.assertEqual(validate_timeout(0), 0)
        self.assertEqual(validate_timeout(30), 30)

    def test_validate_timeout_rejects_below_minus_one(self):
        with self.assertRaises(ValueError):
            validate_timeout(-2)

    def test_describe_timeout(self):
        self.assertEqual(describe_timeout(-1), "none")
        self.assertEqual(describe_timeout(None), "none")
        self.assertEqual(describe_timeout(30), "30s")


# ----------------------------------------------------------------------
# TimeoutManager
# ----------------------------------------------------------------------


class TestTimeoutManagerNoTimeout(unittest.TestCase):
    """The timeout manager must not give up when told not to."""

    def test_default_is_no_timeout(self):
        self.assertEqual(TimeoutManager().default_timeout, -1)

    def test_prompt_waits_indefinitely(self):
        """A prompt that outlives any finite timeout still gets answered."""

        async def slow_answer():
            await asyncio.sleep(1.2)
            return "the answer"

        async def run():
            mgr = TimeoutManager()  # default: -1 == no timeout
            return await mgr.prompt_with_timeout(slow_answer)

        answer, timed_out = asyncio.run(run())
        self.assertEqual(answer, "the answer")
        self.assertFalse(timed_out)

    def test_explicit_no_timeout_argument_waits(self):
        async def slow_answer():
            await asyncio.sleep(1.2)
            return "the answer"

        async def run():
            mgr = TimeoutManager(default_timeout=1)
            return await mgr.prompt_with_timeout(slow_answer, timeout=-1)

        answer, timed_out = asyncio.run(run())
        self.assertEqual(answer, "the answer")
        self.assertFalse(timed_out)

    def test_finite_timeout_still_times_out(self):
        """The no-timeout default must not disable real timeouts."""

        async def slow_answer():
            await asyncio.sleep(5)
            return "never"

        async def run():
            mgr = TimeoutManager(default_timeout=1)
            return await mgr.prompt_with_timeout(slow_answer)

        answer, timed_out = asyncio.run(run())
        self.assertTrue(timed_out)
        self.assertEqual(answer, "")

    def test_retry_variant_waits_indefinitely(self):
        async def slow_answer():
            await asyncio.sleep(1.2)
            return "the answer"

        async def run():
            mgr = TimeoutManager()
            return await mgr.prompt_with_retry(slow_answer, max_retries=0)

        answer, timed_out, attempts = asyncio.run(run())
        self.assertEqual(answer, "the answer")
        self.assertFalse(timed_out)
        self.assertEqual(attempts, 1)


# ----------------------------------------------------------------------
# Console input module
# ----------------------------------------------------------------------


class TestConsoleInputNoTimeout(unittest.TestCase):
    """The console prompt must wait for the human."""

    def test_default_signature_is_no_timeout(self):
        import inspect

        sig = inspect.signature(ConsoleInputModule.prompt_with_status)
        self.assertEqual(sig.parameters["timeout"].default, -1)

    def test_prompt_with_status_waits_indefinitely(self):
        """The input is read after a delay that exceeds any finite timeout."""

        def delayed_input(_msg):
            # The prompt runs in an executor thread, so a blocking sleep is
            # the honest simulation of a slow human.
            time.sleep(1.5)
            return "hello"

        async def run():
            with patch("builtins.input", side_effect=delayed_input):
                return await ConsoleInputModule.prompt_with_status(
                    message="Your response: ",
                    default="fallback",
                    timeout=-1,
                )

        response, was_timeout = asyncio.run(run())
        self.assertEqual(response, "hello")
        self.assertFalse(was_timeout)

    def test_finite_timeout_still_times_out(self):
        """A finite timeout must still expire."""

        def delayed_input(_msg):
            time.sleep(5)
            return "hello"

        async def run():
            with patch("builtins.input", side_effect=delayed_input):
                return await ConsoleInputModule.prompt_with_status(
                    message="Your response: ",
                    default="fallback",
                    timeout=1,
                )

        response, was_timeout = asyncio.run(run())
        self.assertEqual(response, "fallback")
        self.assertTrue(was_timeout)


# ----------------------------------------------------------------------
# The component defaults
# ----------------------------------------------------------------------


class TestComponentDefaults(unittest.TestCase):
    """Every component in the HITL chain defaults to "no timeout"."""

    def test_human_loop_handler(self):
        self.assertEqual(HumanLoopHandler().default_timeout, -1)

    def test_human_loop_handler_keeps_minus_one(self):
        """The old ``max(1, ...)`` clamp turned -1 into 1 second."""
        self.assertEqual(HumanLoopHandler(default_timeout=-1).default_timeout, -1)

    def test_human_loop_handler_rejects_below_minus_one(self):
        with self.assertRaises(ValueError):
            HumanLoopHandler(default_timeout=-2)

    def test_agent_question_event(self):
        event = AgentQuestionEvent(question="Ready?", question_id="q-1")
        self.assertEqual(event.timeout, -1)
        event.validate()  # must not raise

    def test_event_consumer(self):
        consumer = EventConsumer(
            spinner_controller=MagicMock(),
            state_handler=MagicMock(),
            console=MagicMock(),
        )
        self.assertEqual(consumer.hitl_timeout, -1)

    def test_tui_state_bridge(self):
        from components.tui.state_bridge import TuiState

        state = TuiState()
        self.assertEqual(state.hitl_timeout, -1)
        # No countdown is shown when there is no timeout.
        state.hitl_active = True
        state.hitl_start_time = time.time()
        self.assertIsNone(state.get_hitl_time_remaining())


# ----------------------------------------------------------------------
# The agent step — the "timeout + 5" trap
# ----------------------------------------------------------------------


class TestHitlAgentNoTimeout(unittest.TestCase):
    """The agent step must not turn "no timeout" into a short deadline."""

    def test_agent_default_is_no_timeout(self):
        from components.hitl_agent import HITLFunctionAgent
        from llama_index.core.llms.mock import MockFunctionCallingLLM

        agent = HITLFunctionAgent(
            name="test",
            llm=MockFunctionCallingLLM(),
        )
        self.assertEqual(agent.hitl_default_timeout, -1)

    def _make_ctx(self, recorded):
        """A context double that records the wait_for_event() timeout."""

        ctx = MagicMock()
        ctx.store = MagicMock()

        memory = MagicMock()
        memory.aget = AsyncMock(return_value=[])

        async def store_get(key, default=None):
            # The scratchpad is a list; the memory is a Memory object.
            if "scratchpad" in key:
                return []
            if key == "memory":
                return memory
            return default

        ctx.store.get = AsyncMock(side_effect=store_get)
        ctx.store.set = AsyncMock(return_value=None)

        async def wait_for_event(event_type, waiter_event=None, waiter_id=None,
                                 requirements=None, timeout=2000):
            recorded["timeout"] = timeout
            recorded["waiter_event"] = waiter_event
            from components.hitl_events import AgentAnswerEvent

            return AgentAnswerEvent(question_id="q-1", answer="yes")

        ctx.wait_for_event = wait_for_event
        return ctx

    def _run_step(self, hitl_default_timeout):
        from components.hitl_agent import HITLFunctionAgent
        from llama_index.core.agent.workflow import AgentOutput
        from llama_index.core.base.llms.types import ChatMessage, ChatResponse
        from llama_index.core.llms.mock import MockFunctionCallingLLM

        recorded = {}
        ctx = self._make_ctx(recorded)

        agent = HITLFunctionAgent(
            name="test",
            llm=MockFunctionCallingLLM(),
            hitl_enabled=True,
            hitl_default_timeout=hitl_default_timeout,
        )

        message = ChatMessage(role="assistant", content="Shall I proceed?")
        response = ChatResponse(
            message=message,
            raw={"message": {"content": "Shall I proceed?"}},
        )
        event = AgentOutput(
            response=message,
            current_agent_name="test",
            tool_calls=[],
        )

        async def run():
            await agent.parse_agent_output(ctx, event)

        asyncio.run(run())
        return recorded

    def test_no_timeout_means_wait_forever(self):
        """The step must pass timeout=None, not a small number."""
        recorded = self._run_step(-1)
        self.assertIsNone(
            recorded["timeout"],
            "A timeout of -1 must become None (wait forever), "
            f"got {recorded['timeout']!r}",
        )

    def test_finite_timeout_keeps_the_grace_period(self):
        """A finite timeout still gets the 5 second grace period."""
        recorded = self._run_step(10)
        self.assertEqual(recorded["timeout"], 15.0)

    def test_question_event_carries_the_no_timeout(self):
        recorded = self._run_step(-1)
        waiter_event = recorded["waiter_event"]
        self.assertIsInstance(waiter_event, AgentQuestionEvent)
        self.assertEqual(waiter_event.timeout, -1)


# ----------------------------------------------------------------------
# The orchestrators
# ----------------------------------------------------------------------


class TestOrchestratorDefaults(unittest.TestCase):
    """Both entry points default to "no timeout"."""

    def _load(self, name):
        import importlib.util

        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), name
        )
        spec = importlib.util.spec_from_file_location(
            name.replace("-", "_").replace(".py", ""), path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_classic_orchestrator_default(self):
        module = self._load("agent-torvalds.py")
        self.assertEqual(module.HITL_TIMEOUT, -1)
        self.assertEqual(module.hitl_timeout, -1)

    def test_multi_window_orchestrator_default(self):
        module = self._load("agent-torvalds-mw.py")
        self.assertEqual(module.HITL_TIMEOUT, -1)
        self.assertEqual(module.hitl_timeout, -1)

    def _cli_flag_default(self, filename):
        """Return the ``default=`` expression used for ``--hitl-timeout``.

        The parser is built inside ``main()`` and is not exposed, so the
        source is inspected instead.  The default must be the module
        constant, which the other tests pin to -1.
        """
        import ast

        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), filename
        )
        tree = ast.parse(open(path).read())

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "add_argument"):
                continue
            if not node.args:
                continue
            first = node.args[0]
            if not (isinstance(first, ast.Constant) and first.value == "--hitl-timeout"):
                continue
            for kw in node.keywords:
                if kw.arg == "default":
                    return ast.unparse(kw.value)
        return None

    def test_cli_flag_default_is_the_module_constant(self):
        for filename in ("agent-torvalds.py", "agent-torvalds-mw.py"):
            self.assertEqual(
                self._cli_flag_default(filename),
                "HITL_TIMEOUT",
                f"{filename}: --hitl-timeout must default to HITL_TIMEOUT",
            )

    def test_cli_flag_default_resolves_to_no_timeout(self):
        for filename in ("agent-torvalds.py", "agent-torvalds-mw.py"):
            module = self._load(filename)
            self.assertEqual(module.HITL_TIMEOUT, -1)


if __name__ == "__main__":
    unittest.main()
