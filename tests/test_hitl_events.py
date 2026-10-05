"""
Unit tests for HITL (Human-in-the-Loop) event classes.

Tests the custom event types used for agent-human communication:
- AgentQuestionEvent: agent asks a question
- AgentAnswerEvent: human responds to a question
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.hitl_events import (
    AgentQuestionEvent,
    AgentAnswerEvent,
    VALID_INPUT_TYPES,
)


class TestAgentQuestionEventInstantiation(unittest.TestCase):
    """Test that AgentQuestionEvent can be created with all parameter combinations."""

    def test_minimal_construction(self):
        """Event should be creatable with only required fields."""
        event = AgentQuestionEvent(
            question="What is your name?",
            question_id="q-001",
        )
        self.assertEqual(event.question, "What is your name?")
        self.assertEqual(event.question_id, "q-001")
        self.assertEqual(event.timeout, 30)  # default
        self.assertEqual(event.default_answer, "")  # default
        self.assertEqual(event.input_type, "text")  # default
        self.assertEqual(event.options, [])  # default
        self.assertIsNone(event.context)  # default

    def test_full_construction(self):
        """Event should accept all optional parameters."""
        event = AgentQuestionEvent(
            question="Install nginx?",
            question_id="q-002",
            timeout=60,
            default_answer="yes",
            input_type="yesno",
            options=["yes", "no"],
            context="User requested package installation",
        )
        self.assertEqual(event.timeout, 60)
        self.assertEqual(event.default_answer, "yes")
        self.assertEqual(event.input_type, "yesno")
        self.assertEqual(event.options, ["yes", "no"])
        self.assertEqual(event.context, "User requested package installation")

    def test_menu_type_with_options(self):
        """Menu input_type should work with options list."""
        event = AgentQuestionEvent(
            question="Choose a color",
            question_id="q-003",
            input_type="menu",
            options=["red", "green", "blue"],
        )
        self.assertEqual(event.input_type, "menu")
        self.assertEqual(len(event.options), 3)
        self.assertIn("red", event.options)

    def test_password_type(self):
        """Password input_type should be supported."""
        event = AgentQuestionEvent(
            question="Enter password",
            question_id="q-004",
            input_type="password",
        )
        self.assertEqual(event.input_type, "password")

    def test_empty_options_defaults_to_empty_list(self):
        """Passing options=None should default to empty list."""
        event = AgentQuestionEvent(
            question="What now?",
            question_id="q-005",
            options=None,
        )
        self.assertEqual(event.options, [])
        self.assertIsInstance(event.options, list)


class TestAgentQuestionEventValidation(unittest.TestCase):
    """Test the validate() method on AgentQuestionEvent."""

    def test_valid_event_passes(self):
        """A well-formed event should pass validation."""
        event = AgentQuestionEvent(
            question="OK?",
            question_id="q-010",
        )
        event.validate()  # should not raise

    def test_empty_question_raises(self):
        """Empty question should raise ValueError."""
        event = AgentQuestionEvent(
            question="",
            question_id="q-011",
        )
        with self.assertRaises(ValueError) as ctx:
            event.validate()
        self.assertIn("question", str(ctx.exception).lower())

    def test_empty_question_id_raises(self):
        """Empty question_id should raise ValueError."""
        event = AgentQuestionEvent(
            question="Hello?",
            question_id="",
        )
        with self.assertRaises(ValueError) as ctx:
            event.validate()
        self.assertIn("question_id", str(ctx.exception).lower())

    def test_negative_timeout_raises(self):
        """Negative timeout should raise ValueError."""
        event = AgentQuestionEvent(
            question="Hello?",
            question_id="q-012",
            timeout=-5,
        )
        with self.assertRaises(ValueError) as ctx:
            event.validate()
        self.assertIn("timeout", str(ctx.exception).lower())

    def test_invalid_input_type_raises(self):
        """Unknown input_type should raise ValueError."""
        event = AgentQuestionEvent(
            question="Hello?",
            question_id="q-013",
            input_type="invalid_type",
        )
        with self.assertRaises(ValueError) as ctx:
            event.validate()
        self.assertIn("input_type", str(ctx.exception).lower())

    def test_menu_without_options_raises(self):
        """Menu type with no options should raise ValueError."""
        event = AgentQuestionEvent(
            question="Choose?",
            question_id="q-014",
            input_type="menu",
            options=[],
        )
        with self.assertRaises(ValueError) as ctx:
            event.validate()
        self.assertIn("menu", str(ctx.exception).lower())

    def test_all_valid_input_types_pass(self):
        """Every entry in VALID_INPUT_TYPES should pass validation."""
        for itype in VALID_INPUT_TYPES:
            kwargs: dict = {"question": "Q?", "question_id": f"q-{itype}"}
            if itype == "menu":
                kwargs["options"] = ["a", "b"]
            event = AgentQuestionEvent(input_type=itype, **kwargs)
            event.validate()  # should not raise


class TestAgentQuestionEventRepr(unittest.TestCase):
    """Test __repr__ output for debugging friendliness."""

    def test_repr_contains_key_info(self):
        """Repr should include question_id, input_type, and timeout."""
        event = AgentQuestionEvent(
            question="Big question?",
            question_id="q-repr-001",
            timeout=45,
            input_type="yesno",
        )
        r = repr(event)
        self.assertIn("q-repr-001", r)
        self.assertIn("yesno", r)
        self.assertIn("45", r)


class TestAgentAnswerEventInstantiation(unittest.TestCase):
    """Test that AgentAnswerEvent can be created correctly."""

    def test_minimal_construction(self):
        """Event should be creatable with only required fields."""
        event = AgentAnswerEvent(
            question_id="q-001",
            answer="Hello!",
        )
        self.assertEqual(event.question_id, "q-001")
        self.assertEqual(event.answer, "Hello!")
        self.assertFalse(event.was_timeout)

    def test_with_timeout_flag(self):
        """was_timeout=True should be recordable."""
        event = AgentAnswerEvent(
            question_id="q-002",
            answer="default",
            was_timeout=True,
        )
        self.assertTrue(event.was_timeout)

    def test_empty_answer_allowed(self):
        """Empty string answer should be allowed (user declined to answer)."""
        event = AgentAnswerEvent(
            question_id="q-003",
            answer="",
        )
        self.assertEqual(event.answer, "")


class TestAgentAnswerEventValidation(unittest.TestCase):
    """Test the validate() method on AgentAnswerEvent."""

    def test_valid_event_passes(self):
        event = AgentAnswerEvent(question_id="q-020", answer="ok")
        event.validate()  # should not raise

    def test_empty_question_id_raises(self):
        event = AgentAnswerEvent(question_id="", answer="ok")
        with self.assertRaises(ValueError) as ctx:
            event.validate()
        self.assertIn("question_id", str(ctx.exception).lower())


class TestAgentAnswerEventRepr(unittest.TestCase):
    """Test __repr__ output."""

    def test_repr_normal(self):
        event = AgentAnswerEvent(question_id="q-r1", answer="yes")
        r = repr(event)
        self.assertIn("q-r1", r)
        self.assertIn("yes", r)
        self.assertNotIn("timeout", r)

    def test_repr_timeout(self):
        event = AgentAnswerEvent(
            question_id="q-r2", answer="default", was_timeout=True
        )
        r = repr(event)
        self.assertIn("timeout", r)


class TestEventInheritance(unittest.TestCase):
    """Verify events properly inherit from workflows.events.Event."""

    def test_question_event_is_event(self):
        from workflows.events import Event
        q = AgentQuestionEvent(question="Q?", question_id="q-inv")
        self.assertIsInstance(q, Event)

    def test_answer_event_is_event(self):
        from workflows.events import Event
        a = AgentAnswerEvent(question_id="q-inv", answer="A")
        self.assertIsInstance(a, Event)

    def test_question_event_bool(self):
        """Event base class makes `if event:` always True."""
        q = AgentQuestionEvent(question="Q?", question_id="q-bool")
        self.assertTrue(bool(q))

    def test_answer_event_bool(self):
        a = AgentAnswerEvent(question_id="q-bool", answer="A")
        self.assertTrue(bool(a))


class TestValidInputTypesConstant(unittest.TestCase):
    """Verify the VALID_INPUT_TYPES constant."""

    def test_expected_types_present(self):
        for expected in ("text", "yesno", "menu", "password"):
            self.assertIn(expected, VALID_INPUT_TYPES)

    def test_is_frozenset(self):
        self.assertIsInstance(VALID_INPUT_TYPES, frozenset)


if __name__ == "__main__":
    unittest.main()
