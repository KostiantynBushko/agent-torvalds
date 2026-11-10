"""
Tests for the ``\\question`` command — the predefined Human-in-the-Loop test.

The operator asked for it on 2026-11-10: *"a predefined hardcoded test —
when the operator runs a predefined command, for example ``\\question``, the
agent must run HITL to ask some predefined question for the operator, the
agent should not run any tools, just ask the question and process the
response."*

What the tests hold the command to:

* the question travels the **real** HITL path — the same rendering, the
  same input module, the same timeout rules an agent question travels;
* **no tool is run** and the model is not called;
* the answer is **processed** against what the question asked for;
* a timeout is never reported as an answer;
* a secret is never echoed;
* the command asks nothing when the Human-in-the-Loop is off.

Category: HITL / Tests
Retriever Keywords: hitl, question command, predefined, test, round trip
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, List, Optional, Tuple

import pytest

_SELF_DEV = Path(__file__).resolve().parents[1]
if str(_SELF_DEV) not in sys.path:
    sys.path.insert(0, str(_SELF_DEV))

from components.event_consumer import EventConsumer  # noqa: E402
from components.hitl_question import detect_input_type  # noqa: E402
from components.hitl_question_command import (  # noqa: E402
    PREDEFINED_QUESTIONS,
    QuestionCommandRunner,
    command_argument,
    detected_input_type,
    is_question_command,
    process_answer,
    question_by_id,
    render_list,
    run_question_command,
)
from components.spinner_controller import SpinnerController  # noqa: E402
from components.state_handler import StateHandler  # noqa: E402
from rich.console import Console  # noqa: E402


# ---------------------------------------------------------------------------
# The stub input module
# ---------------------------------------------------------------------------

class StubInputModule:
    """An input module that answers with a canned answer.

    It mirrors the **console** input module: a module that offers
    ``prompt_with_status`` answers a yes/no question through its text
    prompt — the answer is normalised by the consumer — and a module that
    does not offer it answers through the confirm widget.

    It records every prompt it receives, so a test can tell *what* the
    operator was asked and *how* — the question decides the prompt, and
    the prompt is what the operator sees.
    """

    #: The consumer renders the question itself.
    renders_question = False

    def __init__(self, answer: str = "", was_timeout: bool = False) -> None:
        self.answer = answer
        self.was_timeout = was_timeout
        #: Every prompt the module received, in order.
        self.prompts: List[dict] = []
        self.input_type: str = ""

    # -- the interface the consumer uses ------------------------------

    def set_input_type(self, input_type: str) -> None:
        self.input_type = input_type
        self.prompts.append({"kind": "type", "value": input_type})

    async def prompt_with_status(
        self,
        message: str = "",
        default: str = "",
        timeout: int = -1,
    ) -> Tuple[str, bool]:
        self.prompts.append({"kind": "text", "message": message})
        if self.was_timeout:
            return default, True
        return self.answer, False

    async def confirm_with_status(
        self,
        message: str = "",
        default_yes: bool = True,
        timeout: int = -1,
    ) -> Tuple[bool, bool]:
        self.prompts.append({"kind": "yesno", "message": message})
        if self.was_timeout:
            return default_yes, True
        return self.answer.strip().lower() in ("y", "yes"), False

    async def menu(self, message: str = "", options: Optional[List[str]] = None,
                   timeout: int = -1) -> str:
        self.prompts.append(
            {"kind": "menu", "message": message, "options": list(options or [])}
        )
        if self.was_timeout:
            return (options or [""])[0]
        return self.answer

    async def menu_with_status(
        self,
        message: str = "",
        options: Optional[List[str]] = None,
        timeout: int = -1,
    ) -> Tuple[str, bool]:
        self.prompts.append(
            {"kind": "menu", "message": message, "options": list(options or [])}
        )
        if self.was_timeout:
            return (options or [""])[0], True
        return self.answer, False

    async def password(self, message: str = "", timeout: int = -1) -> str:
        self.prompts.append({"kind": "password", "message": message})
        return self.answer

    # -- helpers ------------------------------------------------------

    @property
    def kinds(self) -> List[str]:
        """The kinds of the prompts, without the type notification."""
        return [p["kind"] for p in self.prompts if p["kind"] != "type"]


class ConfirmOnlyInputModule(StubInputModule):
    """An input module *without* a text prompt — like the whiptail dialog.

    The consumer falls back to the confirm widget for a yes/no question
    when the module does not offer ``prompt_with_status``.
    """

    prompt_with_status = None  # type: ignore[assignment]

    def __getattribute__(self, name: str) -> Any:
        if name == "prompt_with_status":
            raise AttributeError(name)
        return super().__getattribute__(name)


def _consumer(answer: str = "", was_timeout: bool = False) -> Tuple[
    EventConsumer, StubInputModule
]:
    """Return an ``EventConsumer`` with a stub input module."""
    console = Console(force_terminal=False, width=100)
    consumer = EventConsumer(
        spinner_controller=SpinnerController(console=console),
        state_handler=StateHandler(),
        console=console,
        hitl_timeout=-1,
        hitl_default_answer="",
        hitl_enabled=True,
    )
    stub = StubInputModule(answer=answer, was_timeout=was_timeout)
    consumer.console_input = stub
    return consumer, stub


# ---------------------------------------------------------------------------
# The bank
# ---------------------------------------------------------------------------

class TestTheBank:
    """The bank of predefined questions."""

    def test_the_ids_are_unique(self) -> None:
        ids = [q.id for q in PREDEFINED_QUESTIONS]
        assert len(ids) == len(set(ids)), "the bank has a duplicate id"

    def test_every_question_has_a_text(self) -> None:
        for question in PREDEFINED_QUESTIONS:
            assert question.question.strip(), question.id

    def test_the_bank_covers_every_input_type(self) -> None:
        types = {q.input_type for q in PREDEFINED_QUESTIONS}
        assert types == {"text", "yesno", "menu", "password"}

    def test_a_menu_question_has_options(self) -> None:
        for question in PREDEFINED_QUESTIONS:
            if question.input_type == "menu":
                assert len(question.options) >= 2, question.id
            else:
                assert not question.options, question.id

    def test_the_rules_agree_with_the_bank(self) -> None:
        """The declared type is the type the rules detect.

        The bank is the acceptance criterion of the rules in
        ``components.hitl_question``: a question that is meant to be a
        menu must be detected as a menu, and a question that is meant to
        be a secret must be detected as a secret.  When the rules change,
        this test says so.
        """
        for question in PREDEFINED_QUESTIONS:
            detected = detect_input_type(question.question, question.options)
            assert detected == question.input_type, (
                f"{question.id}: the bank says {question.input_type!r}, the "
                f"rules say {detected!r}"
            )

    def test_detected_input_type_matches_the_rules(self) -> None:
        for question in PREDEFINED_QUESTIONS:
            assert detected_input_type(question) == detect_input_type(
                question.question, question.options
            )

    def test_a_question_is_found_by_its_id(self) -> None:
        found = question_by_id("text-01")
        assert found is not None
        assert found.id == "text-01"

    def test_the_id_is_matched_case_insensitively(self) -> None:
        assert question_by_id("TEXT-01") is not None

    def test_an_unknown_id_is_not_found(self) -> None:
        assert question_by_id("nope") is None
        assert question_by_id("") is None


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------

class TestTheCommand:
    """The recognition of the command."""

    @pytest.mark.parametrize(
        "cmd",
        ["\\question", "\\QUESTION", "  \\question  ", "\\q", "\\Q", "\\question list"],
    )
    def test_the_command_is_recognised(self, cmd: str) -> None:
        assert is_question_command(cmd) is True

    @pytest.mark.parametrize(
        "cmd",
        ["\\stats", "\\help", "\\hitl-status", "question", "", None],
    )
    def test_another_command_is_not_recognised(self, cmd: Optional[str]) -> None:
        assert is_question_command(cmd) is False

    def test_the_argument_is_read(self) -> None:
        assert command_argument("\\question text-01") == "text-01"
        assert command_argument("\\question") == ""
        assert command_argument("\\question   list  ") == "list"

    def test_the_command_is_registered(self) -> None:
        from components.command_registry import COMMAND_SPECS

        names = [spec.name for spec in COMMAND_SPECS]
        assert "\\question" in names

    def test_the_command_is_in_the_help_screen(self) -> None:
        from components.command_registry import HelpOptions, build_help_text

        text = build_help_text(HelpOptions(hitl=True))
        assert "\\question" in text


# ---------------------------------------------------------------------------
# The round trip
# ---------------------------------------------------------------------------

class TestTheRoundTrip:
    """The question is asked through the real HITL path."""

    @pytest.mark.asyncio
    async def test_a_text_question_is_asked_and_answered(self) -> None:
        consumer, stub = _consumer(answer="feature/my-branch")
        runner = QuestionCommandRunner()

        report = await runner.run("\\question text-01", consumer)

        assert report is not None
        assert "feature/my-branch" in report
        assert "What is the name of the branch" in report
        # The question went through the HITL path — the consumer counted it.
        assert consumer.get_hitl_stats()["question_count"] == 1
        # The operator was asked for free text.
        assert stub.kinds == ["text"]
        assert stub.input_type == "text"

    @pytest.mark.asyncio
    async def test_a_yes_no_question_asks_for_a_yes_or_a_no(self) -> None:
        """The console input module answers a yes/no through its prompt.

        The answer is normalised: ``y`` becomes ``yes``, and the report
        says ``yes``.
        """
        consumer, stub = _consumer(answer="y")
        runner = QuestionCommandRunner()

        report = await runner.run("\\question yesno-01", consumer)

        assert report is not None
        assert "| Answer | yes |" in report
        assert stub.kinds == ["text"]
        assert stub.input_type == "yesno"

    @pytest.mark.asyncio
    async def test_a_yes_no_question_uses_the_confirm_widget(self) -> None:
        """A module without a text prompt gets the confirm widget."""
        console = Console(force_terminal=False, width=100)
        consumer = EventConsumer(
            spinner_controller=SpinnerController(console=console),
            state_handler=StateHandler(),
            console=console,
            hitl_timeout=-1,
            hitl_default_answer="",
            hitl_enabled=True,
        )
        stub = ConfirmOnlyInputModule(answer="yes")
        consumer.console_input = stub
        runner = QuestionCommandRunner()

        report = await runner.run("\\question yesno-01", consumer)

        assert report is not None
        assert "| Answer | yes |" in report
        assert stub.kinds == ["yesno"]
        assert stub.input_type == "yesno"

    @pytest.mark.asyncio
    async def test_a_menu_question_offers_its_choices(self) -> None:
        consumer, stub = _consumer(answer="the open ports")
        runner = QuestionCommandRunner()

        report = await runner.run("\\question menu-01", consumer)

        assert report is not None
        assert "the open ports" in report
        assert stub.kinds == ["menu"]
        assert stub.input_type == "menu"
        # The choices were offered to the operator.
        menu = [p for p in stub.prompts if p["kind"] == "menu"][0]
        assert "the disk usage" in menu["options"]

    @pytest.mark.asyncio
    async def test_a_password_question_uses_the_hidden_prompt(self) -> None:
        consumer, stub = _consumer(answer="s3cret")
        runner = QuestionCommandRunner()

        report = await runner.run("\\question password-01", consumer)

        assert report is not None
        assert stub.kinds == ["password"]
        assert stub.input_type == "password"
        # The secret is never echoed — not into the report.
        assert "s3cret" not in report

    @pytest.mark.asyncio
    async def test_no_tool_is_run_and_the_model_is_not_called(self) -> None:
        """The command tests the HITL path — nothing else.

        The agent is never asked anything, so no tool can have been run:
        the workflow was never started.
        """
        consumer, stub = _consumer(answer="yes")
        runner = QuestionCommandRunner()

        report = await runner.run("\\question yesno-01", consumer)

        assert report is not None
        assert "none" in report.lower()
        # No workflow was started — the agent was never called.
        assert consumer._current_handler is None
        # The answer was collected by the input module, once.
        assert len(stub.kinds) == 1

    @pytest.mark.asyncio
    async def test_the_question_is_asked_only_once(self) -> None:
        consumer, stub = _consumer(answer="yes")
        runner = QuestionCommandRunner()

        await runner.run("\\question yesno-01", consumer)

        assert consumer.get_hitl_stats()["question_count"] == 1
        assert consumer.get_hitl_stats()["timeout_count"] == 0

    @pytest.mark.asyncio
    async def test_the_answer_is_recorded_in_the_history(self) -> None:
        from components.human_loop_handler import HumanLoopHandler

        handler = HumanLoopHandler()
        consumer, stub = _consumer(answer="yes")
        consumer.set_human_loop_handler(handler)
        runner = QuestionCommandRunner()

        await runner.run("\\question yesno-01", consumer)

        history = handler.get_question_history()
        assert history, "the question was not recorded"
        assert history[-1]["answer"] == "yes"

    @pytest.mark.asyncio
    async def test_the_questions_are_asked_in_turn(self) -> None:
        """Two runs ask two different questions."""
        consumer, stub = _consumer(answer="yes")
        runner = QuestionCommandRunner()

        first = await runner.run("\\question", consumer)
        second = await runner.run("\\question", consumer)

        assert first is not None and second is not None
        assert first != second

    @pytest.mark.asyncio
    async def test_a_timeout_is_not_reported_as_an_answer(self) -> None:
        consumer, stub = _consumer(answer="", was_timeout=True)
        runner = QuestionCommandRunner()

        report = await runner.run("\\question yesno-01", consumer)

        assert report is not None
        assert "nobody answered" in report.lower()
        assert consumer.get_hitl_stats()["timeout_count"] == 1

    @pytest.mark.asyncio
    async def test_the_command_asks_nothing_when_hitl_is_off(self) -> None:
        consumer, stub = _consumer(answer="yes")
        runner = QuestionCommandRunner()

        report = await runner.run("\\question yesno-01", consumer, hitl_enabled=False)

        assert report is not None
        assert "not asked" in report.lower()
        # Nothing was asked, so nothing was answered.
        assert stub.kinds == []
        assert consumer.get_hitl_stats()["question_count"] == 0

    @pytest.mark.asyncio
    async def test_the_list_asks_nothing(self) -> None:
        consumer, stub = _consumer(answer="yes")
        runner = QuestionCommandRunner()

        report = await runner.run("\\question list", consumer)

        assert report is not None
        for question in PREDEFINED_QUESTIONS:
            assert question.id in report
        assert stub.kinds == []

    @pytest.mark.asyncio
    async def test_an_unknown_id_asks_nothing(self) -> None:
        consumer, stub = _consumer(answer="yes")
        runner = QuestionCommandRunner()

        report = await runner.run("\\question nope", consumer)

        assert report is not None
        assert "nope" in report
        assert stub.kinds == []

    @pytest.mark.asyncio
    async def test_another_command_is_not_run(self) -> None:
        consumer, stub = _consumer(answer="yes")

        report = await run_question_command("\\stats", consumer)

        assert report is None
        assert stub.kinds == []


# ---------------------------------------------------------------------------
# The processing of the answer
# ---------------------------------------------------------------------------

class TestTheProcessing:
    """The answer is checked against what the question asked for."""

    def test_a_yes_is_yes(self) -> None:
        question = question_by_id("yesno-01")
        assert question is not None
        outcome = process_answer(question, "y")
        assert outcome.answer == "yes"
        assert outcome.valid is True

    def test_a_no_is_no(self) -> None:
        question = question_by_id("yesno-01")
        assert question is not None
        outcome = process_answer(question, "No")
        assert outcome.answer == "no"
        assert outcome.valid is True

    def test_anything_else_is_not_a_yes_or_a_no(self) -> None:
        question = question_by_id("yesno-01")
        assert question is not None
        outcome = process_answer(question, "maybe")
        assert outcome.valid is False
        assert "yes" in outcome.note

    def test_a_choice_of_the_menu_is_valid(self) -> None:
        question = question_by_id("menu-01")
        assert question is not None
        outcome = process_answer(question, "the running services")
        assert outcome.answer == "the running services"
        assert outcome.valid is True

    def test_an_answer_outside_the_menu_is_not_valid(self) -> None:
        question = question_by_id("menu-01")
        assert question is not None
        outcome = process_answer(question, "something else")
        assert outcome.valid is False

    def test_a_secret_is_never_echoed(self) -> None:
        question = question_by_id("password-01")
        assert question is not None
        outcome = process_answer(question, "s3cret")
        assert outcome.answer == ""
        assert "s3cret" not in outcome.note

    def test_a_timeout_is_not_an_answer(self) -> None:
        question = question_by_id("text-01")
        assert question is not None
        outcome = process_answer(question, "", was_timeout=True)
        assert outcome.was_timeout is True
        assert outcome.valid is False
        assert outcome.answer == ""

    def test_free_text_is_kept(self) -> None:
        question = question_by_id("text-01")
        assert question is not None
        outcome = process_answer(question, "  feature/my-branch  ")
        assert outcome.answer == "feature/my-branch"
        assert outcome.valid is True


# ---------------------------------------------------------------------------
# The multi-window TUI
# ---------------------------------------------------------------------------

def _tui_app(consumer: EventConsumer):
    """Return a ``TuiApp`` with a stubbed agent and the given consumer."""
    from unittest.mock import MagicMock

    from components.tui.state_bridge import TuiState
    from components.tui.tui_app import TuiApp

    state = TuiState()
    app = TuiApp(
        agent=MagicMock(),
        prompt_handler_fn=MagicMock(),
        state=state,
        console=MagicMock(),
        event_consumer=consumer,
    )
    return app, state


class TestTheTui:
    """The multi-window TUI knows the command as well."""

    @pytest.mark.asyncio
    async def test_the_tui_asks_the_question_and_shows_the_outcome(self) -> None:
        consumer, stub = _consumer(answer="yes")
        app, state = _tui_app(consumer)

        await app._run_question_command("\\question yesno-01")

        assert "yes" in state.markdown_content
        assert stub.kinds, "the operator was not asked"

    @pytest.mark.asyncio
    async def test_the_tui_never_sends_the_command_to_the_agent(self) -> None:
        """The command is a HITL test — the agent is never asked."""
        consumer, stub = _consumer(answer="yes")
        app, state = _tui_app(consumer)

        app.state.input_buffer = "\\question yesno-01"
        app._handle_enter_pressed()

        assert app._active_query_task is None
        app.prompt_handler_fn.assert_not_called()


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------

class TestTheReport:
    """The report the operator reads."""

    def test_the_list_names_every_question(self) -> None:
        text = render_list()
        for question in PREDEFINED_QUESTIONS:
            assert question.id in text
            assert question.question in text

    @pytest.mark.asyncio
    async def test_the_report_names_the_question_and_the_answer(self) -> None:
        consumer, stub = _consumer(answer="the disk usage")
        runner = QuestionCommandRunner()

        report = await runner.run("\\question menu-01", consumer)

        assert report is not None
        assert "menu-01" in report
        assert "Which of these should I check first?" in report
        assert "the disk usage" in report
