"""
Integration tests for complex HITL (Human-in-the-Loop) workflows.

Tests realistic multi-step scenarios combining:
- AgentQuestionEvent / AgentAnswerEvent creation and validation
- TimeoutManager with retries and timeout handling
- HITLRuntimeToggle state management during workflows
- Console input module interactions
- Whiptail input module fallbacks
- Event consumer input handling
- Statistics tracking across multiple operations

These tests simulate real-world agent workflows where the agent:
1. Asks questions with timeouts
2. Handles user responses or timeouts
3. Toggles HITL on/off mid-workflow
4. Tracks statistics across operations
"""
import unittest
import asyncio
import os
import sys
from unittest.mock import patch, MagicMock, AsyncMock, call
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.hitl_events import AgentQuestionEvent, AgentAnswerEvent, VALID_INPUT_TYPES
from components.timeout_manager import TimeoutManager
from components.hitl_runtime_toggle import HITLRuntimeToggle
from components.console_input_module import ConsoleInputModule


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(coro):
    """Run a coroutine on a fresh event loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.run_until_complete(asyncio.sleep(0))
        loop.close()


# ---------------------------------------------------------------------------
# Workflow: Question → Answer Round-Trip
# ---------------------------------------------------------------------------

class TestQuestionAnswerRoundTrip(unittest.TestCase):
    """Test complete question→answer cycles."""

    def test_text_question_and_answer(self):
        """Create a text question event, validate it, and create matching answer."""
        q = AgentQuestionEvent(
            question="What is your name?",
            question_id="name-q-001",
            input_type="text",
            timeout=30,
            default_answer="anonymous",
        )
        q.validate()

        a = AgentAnswerEvent(
            question_id="name-q-001",
            answer="Alice",
            was_timeout=False,
        )
        a.validate()

        # Verify linkage
        self.assertEqual(q.question_id, a.question_id)
        self.assertEqual(q.input_type, "text")
        self.assertFalse(a.was_timeout)

    def test_yesno_question_and_answer(self):
        """Create a yesno question and simulate user confirmation."""
        q = AgentQuestionEvent(
            question="Install nginx?",
            question_id="install-q-001",
            input_type="yesno",
            timeout=60,
            default_answer="yes",
            context="User requested package installation",
        )
        q.validate()

        a = AgentAnswerEvent(
            question_id="install-q-001",
            answer="yes",
            was_timeout=False,
        )
        a.validate()

        self.assertEqual(q.context, "User requested package installation")
        self.assertEqual(q.default_answer, "yes")

    def test_menu_question_and_answer(self):
        """Create a menu question with options and simulate selection."""
        q = AgentQuestionEvent(
            question="Choose a server:",
            question_id="server-q-001",
            input_type="menu",
            options=["nginx", "apache", "caddy"],
            timeout=45,
            default_answer="nginx",
        )
        q.validate()

        # Simulate selecting apache (index 1)
        a = AgentAnswerEvent(
            question_id="server-q-001",
            answer="apache",
            was_timeout=False,
        )
        a.validate()

        self.assertEqual(len(q.options), 3)
        self.assertIn("apache", q.options)

    def test_timeout_answer(self):
        """Simulate a timeout answer using default."""
        q = AgentQuestionEvent(
            question="Proceed?",
            question_id="timeout-q-001",
            input_type="yesno",
            timeout=5,
            default_answer="no",
        )
        q.validate()

        a = AgentAnswerEvent(
            question_id="timeout-q-001",
            answer="no",  # default answer used
            was_timeout=True,
        )
        a.validate()

        self.assertTrue(a.was_timeout)
        self.assertEqual(a.answer, q.default_answer)

    def test_password_question(self):
        """Create a password question."""
        q = AgentQuestionEvent(
            question="Enter sudo password:",
            question_id="pwd-q-001",
            input_type="password",
            timeout=120,
            default_answer="",
        )
        q.validate()

        a = AgentAnswerEvent(
            question_id="pwd-q-001",
            answer="secret123",
            was_timeout=False,
        )
        a.validate()

        self.assertEqual(q.input_type, "password")


# ---------------------------------------------------------------------------
# Workflow: Timeout Manager with Multiple Prompts
# ---------------------------------------------------------------------------

class TestTimeoutManagerWorkflow(unittest.TestCase):
    """Test TimeoutManager across a sequence of prompts."""

    def test_mixed_fast_and_slow_prompts(self):
        """Simulate a workflow with some fast and some slow responses."""
        async def _():
            mgr = TimeoutManager(default_timeout=2)
            results = []

            # Fast answer
            async def fast():
                return "fast"
            a1, t1 = await mgr.prompt_with_timeout(
                fast,
                timeout=5,
                question_id="q1",
            )
            results.append(("q1", a1, t1))

            # Slow answer → timeout
            async def slow():
                await asyncio.sleep(10)
                return "late"
            a2, t2 = await mgr.prompt_with_timeout(
                slow,
                timeout=1,
                default_answer="fallback",
                question_id="q2",
            )
            results.append(("q2", a2, t2))

            # Another fast answer
            async def fast2():
                return "also_fast"
            a3, t3 = await mgr.prompt_with_timeout(
                fast2,
                timeout=5,
                question_id="q3",
            )
            results.append(("q3", a3, t3))

            return results, mgr.get_stats()

        results, stats = run(_())

        # First was fast
        self.assertEqual(results[0], ("q1", "fast", False))
        # Second timed out
        self.assertEqual(results[1], ("q2", "fallback", True))
        # Third was fast
        self.assertEqual(results[2], ("q3", "also_fast", False))
        # Stats show 1 timeout
        self.assertEqual(stats["total_timeouts"], 1)

    def test_retry_workflow(self):
        """Test retry logic across multiple attempts."""
        async def _():
            call_count = {"val": 0}

            async def flaky_prompt():
                call_count["val"] += 1
                if call_count["val"] <= 2:
                    await asyncio.sleep(10)  # will timeout
                return "final_answer"

            mgr = TimeoutManager(default_timeout=1)
            answer, timed_out, attempts = await mgr.prompt_with_retry(
                flaky_prompt,
                timeout=1,
                max_retries=3,
                retry_delay=0.01,
                default_answer="gave_up",
                question_id="retry-q",
            )
            return answer, timed_out, attempts

        answer, timed_out, attempts = run(_())
        self.assertEqual(answer, "final_answer")
        self.assertFalse(timed_out)
        self.assertEqual(attempts, 3)

    def test_all_retries_fail(self):
        """All retries timeout → returns default."""
        async def _():
            async def always_slow():
                await asyncio.sleep(10)
                return "never"

            mgr = TimeoutManager(default_timeout=1)
            answer, timed_out, attempts = await mgr.prompt_with_retry(
                always_slow,
                timeout=1,
                max_retries=2,
                retry_delay=0.01,
                default_answer="default",
            )
            return answer, timed_out, attempts

        answer, timed_out, attempts = run(_())
        self.assertEqual(answer, "default")
        self.assertTrue(timed_out)
        self.assertEqual(attempts, 3)  # 1 initial + 2 retries


# ---------------------------------------------------------------------------
# Workflow: Runtime Toggle During Execution
# ---------------------------------------------------------------------------

class TestRuntimeToggleWorkflow(unittest.TestCase):
    """Test HITLRuntimeToggle state changes during a workflow."""

    def test_toggle_mid_workflow(self):
        """Toggle HITL off and on during execution."""
        async def _():
            toggle = HITLRuntimeToggle(initial_state=True)

            # Start enabled
            self.assertTrue(toggle.is_enabled)

            # User disables HITL
            new_state = await toggle.toggle(source="user")
            self.assertFalse(new_state)
            self.assertEqual(toggle.toggle_count, 1)

            # Continue workflow with HITL off
            self.assertFalse(toggle.is_enabled)

            # Re-enable HITL
            new_state = await toggle.toggle(source="interactive")
            self.assertTrue(new_state)
            self.assertEqual(toggle.toggle_count, 2)

            return toggle.get_toggle_history()

        history = run(_())
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["source"], "user")
        self.assertEqual(history[1]["source"], "interactive")

    def test_command_based_toggle(self):
        """Process commands to toggle HITL."""
        async def _():
            toggle = HITLRuntimeToggle(initial_state=True)

            # Check status
            status_msg = await toggle.process_command("hitl-status")
            self.assertIn("ENABLED", status_msg)

            # Toggle off
            off_msg = await toggle.process_command("toggle-hitl")
            self.assertIn("disabled", off_msg.lower())
            self.assertFalse(toggle.is_enabled)

            # Toggle on
            on_msg = await toggle.process_command("hitl-on")
            self.assertEqual(on_msg, "HITL enabled")
            self.assertTrue(toggle.is_enabled)

            return True

        result = run(_())
        self.assertTrue(result)

    def test_env_var_change_during_workflow(self):
        """Environment variable triggers state change."""
        async def _():
            toggle = HITLRuntimeToggle(initial_state=True, env_var="WORKFLOW_HITL")

            # Initially enabled
            self.assertTrue(toggle.is_enabled)

            # Set env var to disable
            os.environ["WORKFLOW_HITL"] = "false"
            changed = await toggle.check_env_var()
            self.assertTrue(changed)
            self.assertFalse(toggle.is_enabled)

            # Set env var to enable again
            os.environ["WORKFLOW_HITL"] = "1"
            changed = await toggle.check_env_var()
            self.assertTrue(changed)
            self.assertTrue(toggle.is_enabled)

            del os.environ["WORKFLOW_HITL"]
            return True

        result = run(_())
        self.assertTrue(result)


# ---------------------------------------------------------------------------
# Workflow: Console Input Module Sequences
# ---------------------------------------------------------------------------

class TestConsoleInputWorkflow(unittest.TestCase):
    """Test ConsoleInputModule across multiple sequential prompts."""

    def test_multiple_prompts(self):
        """Sequence of text prompts."""
        async def _():
            module = ConsoleInputModule()
            responses = ["Alice", "30", "Python"]

            results = []
            for i, response in enumerate(responses):
                with patch("builtins.input", return_value=response):
                    result = await module.prompt(f"Question {i+1}: ", timeout=5)
                    results.append(result)

            return results

        results = run(_())
        self.assertEqual(results, ["Alice", "30", "Python"])

    def test_confirm_sequence(self):
        """Sequence of yes/no confirmations."""
        async def _():
            module = ConsoleInputModule()
            responses = ["yes", "no", "y", "n"]

            results = []
            for response in responses:
                with patch.object(ConsoleInputModule, "prompt", new_callable=AsyncMock, return_value=response):
                    result = await module.confirm("Proceed?", default_yes=True, timeout=5)
                    results.append(result)

            return results

        results = run(_())
        self.assertEqual(results, [True, False, True, False])

    def test_menu_selection_workflow(self):
        """User goes through a menu selection."""
        async def _():
            module = ConsoleInputModule()

            # User selects option 2
            with patch.object(ConsoleInputModule, "prompt", new_callable=AsyncMock, return_value="2"):
                result = await module.menu(
                    "Choose language:",
                    ["Python", "JavaScript", "Go"],
                    timeout=10,
                )

            return result

        result = run(_())
        self.assertEqual(result, "JavaScript")

    def test_password_then_confirm(self):
        """Password prompt followed by confirmation."""
        async def _():
            module = ConsoleInputModule()

            # Password
            with patch("getpass.getpass", return_value="secret123"):
                pwd = await module.password(timeout=5)

            # Confirm
            with patch.object(ConsoleInputModule, "prompt", new_callable=AsyncMock, return_value="yes"):
                confirmed = await module.confirm("Use this password?", default_yes=True, timeout=5)

            return pwd, confirmed

        pwd, confirmed = run(_())
        self.assertEqual(pwd, "secret123")
        self.assertTrue(confirmed)


# ---------------------------------------------------------------------------
# Workflow: Combined Timeout + Toggle + Events
# ---------------------------------------------------------------------------

class TestCombinedWorkflow(unittest.TestCase):
    """Test workflows combining multiple HITL components."""

    def test_question_timeout_answer_flow(self):
        """Create question → timeout manager handles timeout → answer event."""
        async def _():
            # Create question
            q = AgentQuestionEvent(
                question="Install package?",
                question_id="combo-q-001",
                input_type="yesno",
                timeout=1,
                default_answer="yes",
            )
            q.validate()

            # Timeout manager handles the prompt (simulated timeout)
            mgr = TimeoutManager(default_timeout=1)

            async def slow_user():
                await asyncio.sleep(10)
                return "yes"

            answer, timed_out = await mgr.prompt_with_timeout(
                slow_user,
                timeout=1,
                default_answer=q.default_answer,
                question_id=q.question_id,
            )

            # Create answer event
            a = AgentAnswerEvent(
                question_id=q.question_id,
                answer=answer,
                was_timeout=timed_out,
            )
            a.validate()

            return q, a, mgr.get_stats()

        q, a, stats = run(_())
        self.assertTrue(a.was_timeout)
        self.assertEqual(a.answer, q.default_answer)
        self.assertEqual(stats["total_timeouts"], 1)

    def test_toggle_affects_question_flow(self):
        """HITL toggle controls whether questions are asked."""
        async def _():
            toggle = HITLRuntimeToggle(initial_state=True)
            mgr = TimeoutManager(default_timeout=5)
            questions_asked = []

            # HITL enabled → ask question
            if toggle.is_enabled:
                async def user_response():
                    return "yes"
                answer, timed_out = await mgr.prompt_with_timeout(
                    user_response,
                    timeout=5,
                    question_id="toggle-q-001",
                )
                questions_asked.append(("toggle-q-001", answer))

            # Toggle off
            await toggle.toggle(source="user")
            self.assertFalse(toggle.is_enabled)

            # HITL disabled → skip question
            if toggle.is_enabled:
                questions_asked.append(("toggle-q-002", "should_not_happen"))

            # Toggle back on
            await toggle.toggle(source="user")
            self.assertTrue(toggle.is_enabled)

            # Ask another question
            if toggle.is_enabled:
                async def user_response2():
                    return "no"
                answer, timed_out = await mgr.prompt_with_timeout(
                    user_response2,
                    timeout=5,
                    question_id="toggle-q-002",
                )
                questions_asked.append(("toggle-q-002", answer))

            return questions_asked, toggle.toggle_count

        questions, toggle_count = run(_())
        self.assertEqual(len(questions), 2)
        self.assertEqual(questions[0], ("toggle-q-001", "yes"))
        self.assertEqual(questions[1], ("toggle-q-002", "no"))
        self.assertEqual(toggle_count, 2)

    def test_full_installation_workflow(self):
        """Simulate a package installation workflow with all components."""
        async def _():
            toggle = HITLRuntimeToggle(initial_state=True)
            mgr = TimeoutManager(default_timeout=5)
            events = []

            # Step 1: Confirm installation
            q1 = AgentQuestionEvent(
                question="Install nginx?",
                question_id="install-confirm",
                input_type="yesno",
                timeout=30,
                default_answer="yes",
            )
            q1.validate()

            async def confirm_response():
                return "yes"

            answer1, timed_out1 = await mgr.prompt_with_timeout(
                confirm_response,
                timeout=5,
                question_id=q1.question_id,
            )
            events.append(AgentAnswerEvent(
                question_id=q1.question_id,
                answer=answer1,
                was_timeout=timed_out1,
            ))

            # Step 2: Choose version (menu)
            q2 = AgentQuestionEvent(
                question="Choose nginx version:",
                question_id="install-version",
                input_type="menu",
                options=["stable", "mainline", "legacy"],
                timeout=30,
                default_answer="stable",
            )
            q2.validate()

            async def version_response():
                return "stable"

            answer2, timed_out2 = await mgr.prompt_with_timeout(
                version_response,
                timeout=5,
                question_id=q2.question_id,
            )
            events.append(AgentAnswerEvent(
                question_id=q2.question_id,
                answer=answer2,
                was_timeout=timed_out2,
            ))

            # Step 3: Enter password
            q3 = AgentQuestionEvent(
                question="Enter sudo password:",
                question_id="install-password",
                input_type="password",
                timeout=60,
                default_answer="",
            )
            q3.validate()

            async def password_response():
                return "sudo_pass_123"

            answer3, timed_out3 = await mgr.prompt_with_timeout(
                password_response,
                timeout=5,
                question_id=q3.question_id,
            )
            events.append(AgentAnswerEvent(
                question_id=q3.question_id,
                answer=answer3,
                was_timeout=timed_out3,
            ))

            # Verify all answers
            self.assertEqual(len(events), 3)
            self.assertFalse(events[0].was_timeout)
            self.assertFalse(events[1].was_timeout)
            self.assertFalse(events[2].was_timeout)
            self.assertEqual(events[0].answer, "yes")
            self.assertEqual(events[1].answer, "stable")
            self.assertEqual(events[2].answer, "sudo_pass_123")

            return True

        result = run(_())
        self.assertTrue(result)


# ---------------------------------------------------------------------------
# Workflow: Error Recovery
# ---------------------------------------------------------------------------

class TestErrorRecoveryWorkflow(unittest.TestCase):
    """Test error handling and recovery in workflows."""

    def test_exception_recovery_with_retry(self):
        """Timeout manager recovers from exceptions via retry."""
        async def _():
            call_count = {"val": 0}

            async def flaky_with_exception():
                call_count["val"] += 1
                if call_count["val"] == 1:
                    raise ValueError("first attempt failed")
                if call_count["val"] == 2:
                    await asyncio.sleep(10)  # timeout
                return "success"

            mgr = TimeoutManager(default_timeout=1)
            answer, timed_out, attempts = await mgr.prompt_with_retry(
                flaky_with_exception,
                timeout=1,
                max_retries=3,
                retry_delay=0.01,
                default_answer="gave_up",
            )
            return answer, timed_out, attempts

        answer, timed_out, attempts = run(_())
        self.assertEqual(answer, "success")
        self.assertFalse(timed_out)
        self.assertEqual(attempts, 3)

    def test_consecutive_timeouts_logged_correctly(self):
        """Multiple consecutive timeouts are all logged."""
        async def _():
            async def always_slow():
                await asyncio.sleep(10)
                return "never"

            mgr = TimeoutManager(default_timeout=1)

            for i in range(3):
                await mgr.prompt_with_timeout(
                    always_slow,
                    timeout=1,
                    default_answer=f"default_{i}",
                    question_id=f"timeout_{i}",
                )

            return mgr.get_timeout_log(), mgr.get_stats()

        log, stats = run(_())
        self.assertEqual(len(log), 3)
        self.assertEqual(stats["total_timeouts"], 3)
        self.assertEqual(len(stats["question_ids"]), 3)

    def test_reset_between_workflows(self):
        """Reset timeout manager between workflow runs."""
        async def _():
            mgr = TimeoutManager(default_timeout=1)

            # First workflow
            async def slow():
                await asyncio.sleep(10)
                return "late"
            await mgr.prompt_with_timeout(slow, timeout=1, default_answer="x")
            self.assertEqual(len(mgr.get_timeout_log()), 1)

            # Reset
            mgr.reset()
            self.assertEqual(len(mgr.get_timeout_log()), 0)

            # Second workflow
            async def fast():
                return "fast"
            answer, timed_out = await mgr.prompt_with_timeout(fast, timeout=5)
            self.assertEqual(answer, "fast")
            self.assertFalse(timed_out)
            self.assertEqual(len(mgr.get_timeout_log()), 0)

            return True

        result = run(_())
        self.assertTrue(result)


# ---------------------------------------------------------------------------
# Workflow: Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCaseWorkflows(unittest.TestCase):
    """Edge cases in complex workflows."""

    def test_zero_timeout(self):
        """Zero timeout causes immediate timeout."""
        async def _():
            mgr = TimeoutManager(default_timeout=0)
            async def any_response():
                await asyncio.sleep(1)
                return "value"
            answer, timed_out = await mgr.prompt_with_timeout(
                any_response,
                timeout=0,
                default_answer="immediate",
            )
            return answer, timed_out

        answer, timed_out = run(_())
        self.assertTrue(timed_out)
        self.assertEqual(answer, "immediate")

    def test_very_long_timeout(self):
        """Very long timeout still works with fast response."""
        async def _():
            mgr = TimeoutManager(default_timeout=3600)
            async def instant():
                return "instant"
            answer, timed_out = await mgr.prompt_with_timeout(
                instant,
                timeout=3600,
            )
            return answer, timed_out

        answer, timed_out = run(_())
        self.assertEqual(answer, "instant")
        self.assertFalse(timed_out)

    def test_empty_default_answer(self):
        """Empty string as default answer."""
        async def _():
            mgr = TimeoutManager(default_timeout=1)
            async def slow():
                await asyncio.sleep(10)
                return "late"
            answer, timed_out = await mgr.prompt_with_timeout(
                slow,
                timeout=1,
                default_answer="",
            )
            return answer, timed_out

        answer, timed_out = run(_())
        self.assertTrue(timed_out)
        self.assertEqual(answer, "")

    def test_special_chars_in_question(self):
        """Questions with special characters and unicode."""
        q = AgentQuestionEvent(
            question="Install \U0001f680 nginx (v1.24.0)?",
            question_id="special-q-001",
            input_type="yesno",
            timeout=30,
            default_answer="yes",
        )
        q.validate()
        self.assertIn("\U0001f680", q.question)

    def test_many_options_menu(self):
        """Menu with many options."""
        many_options = [f"option_{i}" for i in range(50)]
        q = AgentQuestionEvent(
            question="Choose:",
            question_id="many-opt-q",
            input_type="menu",
            options=many_options,
            default_answer="option_0",
        )
        q.validate()
        self.assertEqual(len(q.options), 50)


# ---------------------------------------------------------------------------
# Run tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
