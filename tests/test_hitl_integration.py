"""
Integration test for Human-in-the-Loop (HITL) feature.

This test demonstrates the full HITL workflow:
1. Question detection in LLM output
2. User prompting via console/whiptail
3. Timeout handling
4. Runtime toggle (enable/disable HITL)
5. Question history tracking
6. Event streaming with HITL events

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
from components.hitl_events import AgentQuestionEvent, AgentAnswerEvent
from rich.console import Console
from llama_index.core.callbacks.schema import CBEventType, EventPayload


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

    def test_question_history_tracking(self):
        """Test that question history is tracked."""
        async def _run():
            # Mock the prompt to return immediately
            with patch.object(self.handler, '_prompt_user', new_callable=AsyncMock) as mock_prompt:
                mock_prompt.return_value = ("yes", False)
                
                # Simulate handling a question
                await self.handler._handle_question(
                    question="Do you want to continue?",
                    question_id="q1",
                    timeout=5,
                    default_answer="no",
                )
                
                # Check history was recorded
                history = self.handler.get_question_history()
                self.assertEqual(len(history), 1)
                self.assertEqual(history[0]["question_id"], "q1")
                self.assertEqual(history[0]["answer"], "yes")
                self.assertFalse(history[0]["was_timeout"])
        
        asyncio.run(_run())

    def test_timeout_handling(self):
        """Test timeout handling with default answer."""
        async def _run():
            # Mock the prompt to simulate timeout
            with patch.object(self.handler, '_prompt_user', new_callable=AsyncMock) as mock_prompt:
                mock_prompt.return_value = ("default_response", True)
                
                await self.handler._handle_question(
                    question="Question with timeout?",
                    question_id="q2",
                    timeout=5,
                    default_answer="default_response",
                )
                
                # Check timeout was recorded
                timeout_log = self.handler.get_timeout_log()
                self.assertEqual(len(timeout_log), 1)
                self.assertEqual(timeout_log[0]["question_id"], "q2")
        
        asyncio.run(_run())

    def test_deduplication(self):
        """Test that duplicate questions are not asked twice."""
        async def _run():
            call_count = 0
            
            async def mock_prompt(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                return ("answer", False)
            
            with patch.object(self.handler, '_prompt_user', new_callable=AsyncMock, side_effect=mock_prompt):
                # Same question_id should only prompt once
                await self.handler._handle_question(
                    question="First question?",
                    question_id="q1",
                    timeout=5,
                    default_answer="default",
                )
                
                await self.handler._handle_question(
                    question="First question again?",
                    question_id="q1",  # Same ID
                    timeout=5,
                    default_answer="default",
                )
                
                # Different question_id should prompt again
                await self.handler._handle_question(
                    question="Second question?",
                    question_id="q2",
                    timeout=5,
                    default_answer="default",
                )
            
            # Should have prompted only twice (q1 and q2, not q1 duplicate)
            self.assertEqual(call_count, 2)
        
        asyncio.run(_run())

    def test_callback_event_handling(self):
        """Test LlamaIndex callback event handling."""
        async def _run():
            prompt_calls = []
            
            with patch.object(self.handler, '_prompt_user', new_callable=AsyncMock) as mock_prompt:
                mock_prompt.side_effect = lambda *args, **kwargs: prompt_calls.append(args) or (("answer", False),)
                
                # Simulate AGENT_STEP event with question
                self.handler.on_event_start(
                    event_type=CBEventType.AGENT_STEP,
                    payload={
                        EventPayload.COMPLETION: "Do you want to proceed with the operation?"
                    },
                    event_id="event1",
                )
                
                # Give async task time to run
                await asyncio.sleep(0.1)
                
                # Should have detected question and prompted
                self.assertTrue(len(prompt_calls) >= 1)
        
        asyncio.run(_run())

    def test_spinner_pause_resume(self):
        """Test that spinner is paused and resumed during prompts."""
        async def _run():
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
            
            with patch.object(self.handler, '_prompt_user', new_callable=AsyncMock) as mock_prompt:
                mock_prompt.return_value = ("answer", False)
                
                await self.handler._handle_question(
                    question="Question?",
                    question_id="q1",
                    timeout=5,
                    default_answer="default",
                )
            
            self.assertGreaterEqual(pause_count, 1)
            self.assertGreaterEqual(resume_count, 1)
        
        asyncio.run(_run())

    def test_hitl_disabled_skips_questions(self):
        """Test that questions are skipped when HITL is disabled."""
        async def _run():
            # Disable HITL
            self.handler.enable_hitl = False
            
            prompt_calls = []
            with patch.object(self.handler, '_prompt_user', new_callable=AsyncMock) as mock_prompt:
                mock_prompt.side_effect = lambda *args, **kwargs: prompt_calls.append(args) or (("answer", False),)
                
                # Try to trigger question detection
                self.handler.on_event_start(
                    event_type=CBEventType.AGENT_STEP,
                    payload={
                        EventPayload.COMPLETION: "Do you want to proceed?"
                    },
                    event_id="event1",
                )
                
                await asyncio.sleep(0.1)
                
                # Should not have prompted
                self.assertEqual(len(prompt_calls), 0)
        
        asyncio.run(_run())

    def test_reset_clears_history(self):
        """Test that reset clears all state."""
        async def _run():
            # Add some history
            with patch.object(self.handler, '_prompt_user', new_callable=AsyncMock) as mock_prompt:
                mock_prompt.return_value = ("yes", False)
                await self.handler._handle_question(
                    question="Question?",
                    question_id="q1",
                    timeout=5,
                    default_answer="default",
                )
            
            self.assertEqual(len(self.handler.get_question_history()), 1)
            
            # Reset
            self.handler.reset()
            
            # History should be cleared
            self.assertEqual(len(self.handler.get_question_history()), 0)
            self.assertEqual(len(self.handler.get_timeout_log()), 0)
            self.assertEqual(self.handler.question_count, 0)
        
        asyncio.run(_run())

    def test_event_emission(self):
        """Test that HITL events are emitted to event consumer."""
        async def _run():
            # Create mock event consumer
            mock_consumer = AsyncMock()
            self.handler.event_consumer = mock_consumer
            
            with patch.object(self.handler, '_prompt_user', new_callable=AsyncMock) as mock_prompt:
                mock_prompt.return_value = ("yes", False)
                
                await self.handler._handle_question(
                    question="Question?",
                    question_id="q1",
                    timeout=5,
                    default_answer="default",
                )
            
            # Should have emitted question and answer events
            self.assertTrue(mock_consumer.send_event.called)
        
        asyncio.run(_run())


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

    def test_hitl_markers(self):
        """Test detection of explicit HITL markers."""
        self.assertTrue(self.handler._is_question("[HITL] Confirm?"))
        self.assertTrue(self.handler._is_question("[QUESTION] Proceed?"))
        self.assertTrue(self.handler._is_question("[NEEDS_INPUT] What next?"))


if __name__ == "__main__":
    # Run tests
    unittest.main(verbosity=2)
