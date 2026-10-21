"""
Integration test for Human-in-the-Loop (HITL) feature.

This test demonstrates the full HITL workflow:
1. Question detection in LLM output
2. User prompting (performed by the EventConsumer — the single prompt path)
3. Timeout handling
4. Runtime toggle (enable/disable HITL)
5. Question history tracking
6. Event streaming with HITL events

Architecture note
-----------------
Since the fix in ``investigate/hitl-investigate/`` the responsibilities are
split:

* ``HumanLoopHandler`` — detects questions, keeps the history.  It does
  **not** prompt the user.
* ``EventConsumer`` — prompts the user (exactly once per question) and sends
  the answer back to the waiting workflow step.
* ``HITLFunctionAgent`` — raises the question on the workflow event stream
  and waits for the answer.

Run this test to verify HITL is working correctly.
"""
import unittest
import asyncio
import sys
import os
from unittest.mock import Mock, AsyncMock, patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.human_loop_handler import HumanLoopHandler
from components.hitl_runtime_toggle import HITLRuntimeToggle
from components.spinner_controller import SpinnerController
from components.console_input_module import ConsoleInputModule
from components.event_consumer import EventConsumer
from components.state_handler import StateHandler
from components.hitl_events import AgentQuestionEvent, AgentAnswerEvent
from rich.console import Console
from llama_index.core.callbacks.schema import CBEventType, EventPayload
from llama_index.core.base.llms.types import ChatMessage, ChatResponse


class TestHITLIntegration(unittest.TestCase):
    """Integration tests for HITL workflow."""

    def setUp(self):
        """Set up test fixtures."""
        self.console = Console(force_terminal=True, width=80)
        self.spinner = SpinnerController(console=self.console)
        self.toggle = HITLRuntimeToggle(initial_state=True)

        self.handler = HumanLoopHandler(
            input_method="console",
            default_timeout=5,
            default_answer="default_response",
            console=self.console,
            spinner=self.spinner,
            enable_hitl=True,
            runtime_toggle=self.toggle,
        )

    def _make_consumer(self, hitl_enabled: bool = True) -> EventConsumer:
        """Build an EventConsumer wired to the handler."""
        consumer = EventConsumer(
            spinner_controller=self.spinner,
            state_handler=StateHandler(),
            console=self.console,
            hitl_timeout=5,
            hitl_default_answer="default_response",
            hitl_enabled=hitl_enabled,
            human_loop_handler=self.handler,
        )
        return consumer

    def test_hitl_enabled_initially(self):
        """Test that HITL is enabled by default."""
        self.assertTrue(self.handler.enable_hitl)
        self.assertTrue(self.handler._is_hitl_enabled())

    def test_hitl_runtime_toggle(self):
        """Test runtime toggle integration."""
        async def _run():
            # Initially enabled
            self.assertTrue(self.handler._is_hitl_enabled())

            # Toggle off
            await self.toggle.toggle(source="test")
            self.assertFalse(self.handler._is_hitl_enabled())

            # Toggle on again
            await self.toggle.toggle(source="test")
            self.assertTrue(self.handler._is_hitl_enabled())

        asyncio.run(_run())

    def test_question_detection_patterns(self):
        """Test that questions are correctly detected."""
        # Should detect questions
        self.assertTrue(self.handler._is_question("What is the capital of France?"))
        self.assertTrue(self.handler._is_question("Do you want to proceed?"))
        self.assertTrue(self.handler._is_question("Would you like to continue?"))
        self.assertTrue(self.handler._is_question("Please confirm this action"))
        self.assertTrue(self.handler._is_question("Do you want to delete this file?"))
        self.assertTrue(self.handler._is_question("[HITL] Approve this change?"))

        # Should not detect non-questions
        self.assertFalse(self.handler._is_question("This is a statement"))
        self.assertFalse(self.handler._is_question("Processing data..."))
        self.assertFalse(self.handler._is_question("Operation completed successfully"))

    def test_input_type_detection(self):
        """Test heuristic input type detection."""
        # Test _detect_input_type helper
        from components.human_loop_handler import _detect_input_type

        self.assertEqual(_detect_input_type("Enter your password: "), "password")
        self.assertEqual(_detect_input_type("Do you want to proceed?"), "yesno")
        self.assertEqual(_detect_input_type("What is your name?"), "text")
        self.assertEqual(_detect_input_type("Confirm deletion"), "yesno")

    def test_extract_text_from_chat_response(self):
        """The extractor must read the assistant text from a ChatResponse.

        This is investigation defect #1: the text lives in
        ``response.message.content``, not in ``.text`` nor at the top level
        of ``.raw``.
        """
        response = ChatResponse(
            message=ChatMessage(role="assistant", content="Do you want to proceed?"),
            raw={"message": {"role": "assistant", "content": "Do you want to proceed?"}},
        )
        text = self.handler._extract_text(response)
        self.assertEqual(text, "Do you want to proceed?")
        self.assertTrue(self.handler._is_question(text))

    def test_extract_text_from_mock_raw_shape(self):
        """The extractor must also handle the ``raw={"content": ...}`` shape."""
        response = ChatResponse(
            message=ChatMessage(role="assistant", content="Do you want to proceed?"),
            raw={"content": "Do you want to proceed?"},
        )
        self.assertEqual(
            self.handler._extract_text(response), "Do you want to proceed?"
        )

    def test_question_history_tracking(self):
        """Test that the answer is recorded in the question history."""
        consumer = self._make_consumer()
        event = AgentQuestionEvent(
            question="Do you want to continue?",
            question_id="q1",
            timeout=5,
            default_answer="no",
        )

        async def _run():
            with patch.object(
                consumer.console_input, "prompt_with_status", new_callable=AsyncMock
            ) as mock_prompt:
                mock_prompt.return_value = ("yes", False)
                await consumer._on_agent_question(event)

        asyncio.run(_run())

        history = self.handler.get_question_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["question_id"], "q1")
        self.assertEqual(history[0]["answer"], "yes")
        self.assertFalse(history[0]["was_timeout"])

    def test_timeout_handling(self):
        """Test timeout handling with default answer."""
        consumer = self._make_consumer()
        event = AgentQuestionEvent(
            question="Question with timeout?",
            question_id="q2",
            timeout=5,
            default_answer="default_response",
        )

        async def _run():
            with patch.object(
                consumer.console_input, "prompt_with_status", new_callable=AsyncMock
            ) as mock_prompt:
                # An empty response means the user did not answer.
                mock_prompt.return_value = ("", True)
                await consumer._on_agent_question(event)

        asyncio.run(_run())

        timeout_log = self.handler.get_timeout_log()
        self.assertEqual(len(timeout_log), 1)
        self.assertEqual(timeout_log[0]["question_id"], "q2")

    def test_deduplication(self):
        """The consumer must prompt exactly once per question event."""
        consumer = self._make_consumer()
        event = AgentQuestionEvent(
            question="First question?",
            question_id="q1",
            timeout=5,
            default_answer="default",
        )

        async def _run():
            with patch.object(
                consumer.console_input, "prompt_with_status", new_callable=AsyncMock
            ) as mock_prompt:
                mock_prompt.return_value = ("answer", False)
                await consumer._on_agent_question(event)

        asyncio.run(_run())

        self.assertEqual(consumer.get_hitl_stats()["question_count"], 1)

    def test_callback_event_handling(self):
        """LLM callback events are observed and recorded (not prompted).

        The dead ``CBEventType.AGENT_STEP`` branch was removed — llama-index
        never emits that event — so the observation happens on the LLM event.
        """
        response = ChatResponse(
            message=ChatMessage(
                role="assistant", content="Do you want to proceed with the operation?"
            ),
            raw={"message": {"role": "assistant", "content": "Do you want to proceed?"}},
        )

        self.handler.on_event_end(
            event_type=CBEventType.LLM,
            payload={EventPayload.RESPONSE: response},
            event_id="event1",
        )

        history = self.handler.get_question_history()
        self.assertEqual(len(history), 1)
        self.assertIn("Do you want to proceed", history[0]["question"])

    def test_agent_step_branch_is_dead_code(self):
        """``CBEventType.AGENT_STEP`` is never emitted — the branch is inert."""
        before = len(self.handler.get_question_history())
        self.handler.on_event_start(
            event_type=CBEventType.AGENT_STEP,
            payload={EventPayload.COMPLETION: "Do you want to proceed?"},
            event_id="event1",
        )
        self.assertEqual(len(self.handler.get_question_history()), before)

    def test_spinner_pause_resume(self):
        """Test that spinner is paused and resumed during prompts."""
        consumer = self._make_consumer()
        pause_count = 0
        resume_count = 0

        original_pause = self.spinner.pause
        original_resume = self.spinner.resume

        def track_pause():
            nonlocal pause_count
            pause_count += 1
            return original_pause()

        def track_resume():
            nonlocal resume_count
            resume_count += 1
            return original_resume()

        self.spinner.pause = track_pause
        self.spinner.resume = track_resume

        event = AgentQuestionEvent(
            question="Question?",
            question_id="q1",
            timeout=5,
            default_answer="default",
        )

        async def _run():
            with patch.object(
                consumer.console_input, "prompt_with_status", new_callable=AsyncMock
            ) as mock_prompt:
                mock_prompt.return_value = ("answer", False)
                await consumer._on_agent_question(event)

        asyncio.run(_run())

        self.assertGreaterEqual(pause_count, 1)
        self.assertGreaterEqual(resume_count, 1)

    def test_hitl_disabled_skips_questions(self):
        """Test that questions are skipped when HITL is disabled."""
        consumer = self._make_consumer(hitl_enabled=False)
        event = AgentQuestionEvent(
            question="Do you want to proceed?",
            question_id="q1",
            timeout=5,
            default_answer="default",
        )

        async def _run():
            with patch.object(
                consumer.console_input, "prompt_with_status", new_callable=AsyncMock
            ) as mock_prompt:
                await consumer._on_agent_question(event)

        asyncio.run(_run())

        self.assertEqual(consumer.get_hitl_stats()["question_count"], 0)
        self.assertEqual(len(self.handler.get_question_history()), 0)

    def test_reset_clears_history(self):
        """Test that reset clears all state."""
        consumer = self._make_consumer()
        event = AgentQuestionEvent(
            question="Question?",
            question_id="q1",
            timeout=5,
            default_answer="default",
        )

        async def _run():
            with patch.object(
                consumer.console_input, "prompt_with_status", new_callable=AsyncMock
            ) as mock_prompt:
                mock_prompt.return_value = ("yes", False)
                await consumer._on_agent_question(event)

        asyncio.run(_run())

        self.assertEqual(len(self.handler.get_question_history()), 1)

        # Reset
        self.handler.reset()

        # History should be cleared
        self.assertEqual(len(self.handler.get_question_history()), 0)
        self.assertEqual(len(self.handler.get_timeout_log()), 0)
        self.assertEqual(self.handler.question_count, 0)

    def test_event_emission(self):
        """The answer is sent back to the workflow as an AgentAnswerEvent."""
        consumer = self._make_consumer()
        event = AgentQuestionEvent(
            question="Question?",
            question_id="q1",
            timeout=5,
            default_answer="default",
        )

        mock_handler = MagicMock()

        async def _run():
            consumer._current_handler = mock_handler
            with patch.object(
                consumer.console_input, "prompt_with_status", new_callable=AsyncMock
            ) as mock_prompt:
                mock_prompt.return_value = ("yes", False)
                await consumer._on_agent_question(event)

        asyncio.run(_run())

        # The answer must be dispatched to the waiting workflow step.
        mock_handler.ctx.send_event.assert_called_once()
        sent = mock_handler.ctx.send_event.call_args[0][0]
        self.assertIsInstance(sent, AgentAnswerEvent)
        self.assertEqual(sent.answer, "yes")
        self.assertEqual(sent.question_id, "q1")


class TestHITLQuestionDetection(unittest.TestCase):
    """Test question detection patterns."""

    def setUp(self):
        self.handler = HumanLoopHandler()

    def test_question_mark_detection(self):
        """Test detection of questions ending with ?."""
        self.assertTrue(self.handler._is_question("What is 2+2?"))
        self.assertTrue(self.handler._is_question("Are you sure?"))
        self.assertFalse(self.handler._is_question("No question here"))

    def test_confirmation_keywords(self):
        """Test detection of confirmation keywords."""
        self.assertTrue(self.handler._is_question("Please confirm this action"))
        self.assertTrue(self.handler._is_question("Do you approve?"))
        self.assertTrue(self.handler._is_question("Proceed with deletion"))

    def test_destructive_operations(self):
        """Test detection of destructive operation keywords."""
        self.assertTrue(self.handler._is_question("Delete this file"))
        self.assertTrue(self.handler._is_question("Drop the database"))
        self.assertTrue(self.handler._is_question("Remove all data"))

    def test_destructive_operations_need_an_imperative(self):
        """Prose that merely mentions a destructive verb is not a question.

        Without this the agent would keep asking the human the same thing
        forever once the answer was "no".
        """
        self.assertFalse(
            self.handler._is_question("Understood, I will not delete it.")
        )
        self.assertFalse(self.handler._is_question("I deleted the database."))

    def test_hitl_markers(self):
        """Test detection of explicit HITL markers."""
        self.assertTrue(self.handler._is_question("[HITL] Confirm?"))
        self.assertTrue(self.handler._is_question("[QUESTION] Proceed?"))
        self.assertTrue(self.handler._is_question("[NEEDS_INPUT] What next?"))


if __name__ == "__main__":
    # Run tests
    unittest.main(verbosity=2)
