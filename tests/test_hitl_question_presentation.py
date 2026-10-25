"""
Tests for the HITL question presentation.

The Human-in-the-Loop used to treat the **whole assistant message** as the
question.  The operator reported the two symptoms in
``investigate/hitl-questions-issue/``:

* the console showed ``Enter password: `` instead of a yes/no question — a
  report that merely mentioned *"secret redaction"* was classified as a
  password request because the *answer* was searched for the word "secret";
* the same message was rendered twice — once by the consumer, once by the
  input module's prompt.

These tests cover the fix:

* the pure helpers in :mod:`components.hitl_question` (splitting,
  the input type, the normalisation);
* the wiring: the agent puts the question and the context into the event,
  the consumer renders the question exactly once, and the input module
  never sees the question.

Category: HITL / Tests
Retriever Keywords: hitl, question, presentation, split, input type, tests
"""

from __future__ import annotations

import asyncio
import io
import logging
import sys
from pathlib import Path
from typing import Any, List, Sequence, Tuple
from unittest.mock import patch

import pytest

_SELF_DEV = Path(__file__).resolve().parents[1]
if str(_SELF_DEV) not in sys.path:
    sys.path.insert(0, str(_SELF_DEV))

from llama_index.core.base.llms.types import ChatMessage, ChatResponse  # noqa: E402
from llama_index.core.llms.callbacks import llm_chat_callback  # noqa: E402
from llama_index.core.llms.mock import MockFunctionCallingLLM  # noqa: E402
from llama_index.core.tools import FunctionTool  # noqa: E402
from pydantic import Field  # noqa: E402
from rich.console import Console  # noqa: E402

from components.event_consumer import EventConsumer  # noqa: E402
from components.hitl_agent import HITLFunctionAgent  # noqa: E402
from components.hitl_events import AgentQuestionEvent  # noqa: E402
from components.hitl_question import (  # noqa: E402
    MAX_QUESTION_CHARS,
    detect_input_type,
    is_question,
    normalise_question,
    split_question,
)
from components.spinner_controller import SpinnerController  # noqa: E402
from components.state_handler import StateHandler  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures — condensed versions of the two operator-reported payloads
# ---------------------------------------------------------------------------

#: Issue #1 — a long report that ends in a yes/no question.  The operator
#: saw ``Enter password: `` instead of the question.
REPORT_PAYLOAD = """## Done — investigation and proposal delivered

**Deliverables** (in `self-development/investigate/Voice-Output/`):

- `INVESTIGATION_REPORT.md` (683 lines)
- `PROPOSAL_voice_output.md` (883 lines)

### Key findings

**1. The build is already done** — the server is built and the weights are
downloaded:
```
audio.cpp/build/linux-cuda-release/bin/audiocpp_server
```

**2. The agent has zero audio capability** — a grep for `tts|speech|audio`
returns exactly 2 hits, both incidental mentions in a proposal doc.

**3. The hard part isn't synthesis — it's the interface.** Three genuinely
different capabilities are hiding in "produce voice".

**4. Opt-in, off by default, additive (text is always still printed), with
secret redaction on by default.**

### Six open questions I need you to decide before Phase 3

1. Default Kokoro voice (English `af_heart` vs multilingual)?
2. Should enabling voice immediately speak every answer?

Want me to start **Phase 0** (the `text.py` preparation layer) on a `feature/voice-toolkit` branch?
"""

#: Issue #2 — a status report with two questions; the operator saw the whole
#: message twice.
STATUS_PAYLOAD = """I see the project structure. There's no sqitch configuration yet, but there is a `setup_postgres_db.sql` file.

**Current status:**
- On branch `master`, up to date with `origin/master`
- DNS resolution is failing, so I can't pull from remote right now
- No sqitch config found in the project

Let me create a new branch for the feature. What would you like to name it? For example:
- `feature/sqitch-database-migrations`
- `feature/db-migrations`
- Or another name?

Also, would you like me to:
1. Set up sqitch for database version control?
2. Start with documentation for the sqitch integration?"""


# ---------------------------------------------------------------------------
# The pure module
# ---------------------------------------------------------------------------

class TestSplitQuestion:
    """``split_question`` separates the question from the report."""

    def test_splits_report_from_question(self):
        split = split_question(REPORT_PAYLOAD)
        assert split is not None
        assert split.question.startswith("Want me to start")
        assert split.question.endswith("branch?")
        # The question is short, the report is long.
        assert len(split.question) < 200
        assert len(split.context) > 500
        # The report is the context, not part of the question.
        assert "Key findings" in split.context
        assert "Want me to start" not in split.context

    def test_splits_list_question(self):
        split = split_question(STATUS_PAYLOAD)
        assert split is not None
        assert split.question.startswith("Also, would you like me to:")
        assert "1. Set up sqitch" in split.question
        # The earlier question stays visible in the context.
        assert "What would you like to name it?" in split.context
        assert split.options == (
            "Set up sqitch for database version control?",
            "Start with documentation for the sqitch integration?",
        )

    def test_returns_none_without_interrogative(self):
        assert split_question("All done.") is None
        assert split_question("") is None
        assert split_question("   \n  ") is None

    def test_lead_in_is_kept(self):
        split = split_question("Here is what I found:\nShall I proceed?")
        assert split is not None
        assert split.question == "Here is what I found:\nShall I proceed?"

    def test_long_question_is_truncated(self):
        long_question = "Shall I " + ("do the thing " * 200) + "now?"
        split = split_question(long_question)
        assert split is not None
        assert len(split.question) <= MAX_QUESTION_CHARS
        assert split.question.endswith("…")

    def test_context_is_the_rest_of_the_message(self):
        split = split_question("Some context here.\n\nShall I proceed?")
        assert split is not None
        assert split.context == "Some context here."

    def test_a_question_in_the_middle_keeps_the_tail(self):
        split = split_question("Before. Shall I proceed? After.")
        assert split is not None
        assert split.question == "Shall I proceed?"
        assert "Before." in split.context
        assert "After." in split.context


class TestDetectInputType:
    """The input type follows the *question*, never the answer."""

    def test_password_needs_an_ask(self):
        # A report that merely mentions a secret is not a password request.
        assert detect_input_type(
            "Everything works, with secret redaction on by default."
        ) == "text"

    def test_password_question_is_password(self):
        assert detect_input_type("What is the sudo password?") == "password"
        assert detect_input_type("Enter the database password:") == "password"

    def test_yesno_needs_a_binary_offer(self):
        assert detect_input_type("Shall I create the branch x?") == "yesno"
        assert detect_input_type("Would you like me to continue?") == "yesno"
        assert detect_input_type("What is the name of the project?") == "text"

    def test_word_boundaries(self):
        # "no" inside "notification" must not make this a yes/no question.
        assert detect_input_type("Any notification preferences?") == "text"
        assert detect_input_type("Any documentation to update?") == "text"

    def test_menu_when_options_present(self):
        assert detect_input_type(
            "Also, would you like me to:",
            options=["Set up sqitch?", "Write the docs?"],
        ) == "menu"
        # One option is not a choice.
        assert detect_input_type(
            "Also, would you like me to:", options=["Set up sqitch?"]
        ) == "yesno"

    def test_explicit_marker_wins(self):
        assert detect_input_type("[HITL:password] the token") == "password"
        assert detect_input_type("[HITL:yesno] go on") == "yesno"
        assert detect_input_type("[HITL:text] anything") == "text"

    def test_the_report_is_not_a_password(self):
        split = split_question(REPORT_PAYLOAD)
        assert split is not None
        assert detect_input_type(split.question, split.options) != "password"


class TestConsoleInputModule:
    """The status-aware API of the console input module."""

    def _module(self):
        from components.console_input_module import ConsoleInputModule
        return ConsoleInputModule()

    def test_confirm_with_status_reports_an_empty_answer(self):
        module = self._module()
        with patch("components.console_input_module.input", return_value=""):
            confirmed, was_timeout = asyncio.run(
                module.confirm_with_status("[y/N]", default_yes=False, timeout=5)
            )
        assert confirmed is False
        assert was_timeout is True

    def test_confirm_with_status_reports_an_answer(self):
        module = self._module()
        with patch("components.console_input_module.input", return_value="y"):
            confirmed, was_timeout = asyncio.run(
                module.confirm_with_status("[y/N]", default_yes=False, timeout=5)
            )
        assert confirmed is True
        assert was_timeout is False

    def test_menu_with_status_selects_an_option(self):
        module = self._module()
        with patch("components.console_input_module.input", return_value="2"):
            selected, was_timeout = asyncio.run(
                module.menu_with_status(
                    "Select option [1]: ", ["first", "second"], timeout=5
                )
            )
        assert selected == "second"
        assert was_timeout is False

    def test_menu_with_status_defaults_to_the_first_option(self):
        module = self._module()
        with patch("components.console_input_module.input", return_value=""):
            selected, was_timeout = asyncio.run(
                module.menu_with_status(
                    "Select option [1]: ", ["first", "second"], timeout=5
                )
            )
        assert selected == "first"
        assert was_timeout is True

    def test_menu_with_status_ignores_an_invalid_number(self):
        module = self._module()
        with patch("components.console_input_module.input", return_value="99"):
            selected, was_timeout = asyncio.run(
                module.menu_with_status(
                    "Select option [1]: ", ["first", "second"], timeout=5
                )
            )
        assert selected == "first"
        assert was_timeout is False


class TestNormaliseQuestion:
    """The normalisation is the key of the re-ask guard."""

    def test_normalisation_is_stable(self):
        assert normalise_question(
            "Shall I create the branch feature/x?"
        ) == normalise_question(
            "  shall i create the branch `feature/x`?  "
        )

    def test_a_rephrasing_collapses(self):
        assert normalise_question(
            "Shall I create the branch feature/x?"
        ) == normalise_question(
            "Should I create the branch feature/x?"
        )

    def test_different_questions_stay_different(self):
        assert normalise_question(
            "Shall I create the branch feature/x?"
        ) != normalise_question(
            "Shall I delete the branch feature/x?"
        )


class TestIsQuestion:
    def test_code_span_question_is_detected(self):
        assert is_question("Shall I create the branch `feature/sqitch`?")

    def test_a_statement_is_not_a_question(self):
        assert not is_question("This is a statement")

    def test_a_destructive_request_is_a_question(self):
        assert is_question("Please delete the production database")

    def test_prose_that_mentions_a_destructive_verb_is_not(self):
        assert not is_question("Understood, I will not delete it.")


# ---------------------------------------------------------------------------
# The wiring
# ---------------------------------------------------------------------------

def add_two(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


class ScriptedLLM(MockFunctionCallingLLM):
    """Replays a fixed script of assistant messages, one per call."""

    script: List[str] = Field(default_factory=list)
    calls: List[Any] = Field(default_factory=list)

    @llm_chat_callback()
    async def astream_chat(self, messages: Sequence[ChatMessage], **kwargs: Any):
        self.calls.append([(m.role, str(m.content)) for m in messages])
        index = min(len(self.calls) - 1, len(self.script) - 1)
        text = self.script[index]

        async def gen():
            yield ChatResponse(
                message=ChatMessage(role="assistant", content=text),
                delta=text,
                raw={"message": {"role": "assistant", "content": text}},
            )

        return gen()


class RecordingInput:
    """Console input double: records the prompts and replays the answers."""

    def __init__(self, answers: Sequence[str] = ()) -> None:
        self.answers = list(answers)
        self.prompts: List[str] = []

    def _next(self) -> str:
        if not self.answers:
            return ""
        return self.answers.pop(0)

    async def prompt(self, message: str = "", default: str = "", timeout: int = -1) -> str:
        self.prompts.append(message)
        return self._next()

    async def prompt_with_status(
        self, message: str = "", default: str = "", timeout: int = -1
    ) -> Tuple[str, bool]:
        self.prompts.append(message)
        answer = self._next()
        return (answer or default), not answer.strip()

    async def confirm(self, message: str = "", default_yes: bool = True, timeout: int = -1) -> bool:
        self.prompts.append(message)
        answer = self._next()
        if not answer:
            return default_yes
        return answer.strip().lower() in ("y", "yes")

    async def menu(self, message: str = "", options=None, timeout: int = -1) -> str:
        self.prompts.append(message)
        return self._next() or (options or [""])[0]

    async def menu_with_status(
        self, message: str = "", options=None, timeout: int = -1
    ) -> Tuple[str, bool]:
        """Mirrors ``ConsoleInputModule.menu_with_status``."""
        self.prompts.append(message)
        answer = self._next()
        choices = list(options or [])
        if not choices:
            return "", True
        if not answer.strip():
            return choices[0], True
        try:
            index = int(answer.strip()) - 1
            if 0 <= index < len(choices):
                return choices[index], False
        except ValueError:
            pass
        return choices[0], False

    async def password(self, message: str = "", timeout: int = -1) -> str:
        self.prompts.append(message)
        return self._next()


class _LogCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.messages: List[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def run(script: Sequence[str], answers: Sequence[str] = ("no",)) -> dict:
    """Run one scripted conversation through the real HITL stack."""
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=100, highlight=False)

    consumer = EventConsumer(
        spinner_controller=SpinnerController(console=console),
        state_handler=StateHandler(),
        console=console,
        hitl_timeout=-1,
        hitl_default_answer="no",
    )
    recorder = RecordingInput(answers)
    consumer.console_input = recorder

    llm = ScriptedLLM(script=list(script))
    agent = HITLFunctionAgent(
        tools=[FunctionTool.from_defaults(fn=add_two)],
        llm=llm,
        hitl_enabled=True,
        hitl_default_timeout=-1,
        hitl_default_answer="no",
    )

    question_events: List[AgentQuestionEvent] = []
    capture = _LogCapture()
    logger = logging.getLogger("components.hitl_agent")
    logger.setLevel(logging.INFO)
    logger.addHandler(capture)

    async def _drive() -> None:
        handler = agent.run("go")
        original_stream = handler.stream_events

        async def tapped():
            async for event in original_stream():
                if isinstance(event, AgentQuestionEvent):
                    question_events.append(event)
                yield event

        handler.stream_events = tapped
        await consumer.consume_events(handler, "go")

    try:
        asyncio.run(_drive())
    finally:
        logger.removeHandler(capture)

    return {
        "events": question_events,
        "prompts": recorder.prompts,
        "console": buffer.getvalue(),
        "logs": capture.messages,
        "llm_calls": llm.calls,
    }


def _normalise(text: str) -> str:
    return " ".join(text.split())


class TestRendering:
    """The question reaches the operator exactly once."""

    def test_question_rendered_once(self):
        out = run([STATUS_PAYLOAD, "All done."], answers=["no"])
        rendered = _normalise(out["console"]).count(_normalise(STATUS_PAYLOAD))
        assert rendered == 1
        # And the input module does not repeat it.
        assert not any(
            _normalise(STATUS_PAYLOAD) in _normalise(prompt)
            for prompt in out["prompts"]
        )

    def test_context_is_rendered(self):
        out = run([STATUS_PAYLOAD, "All done."], answers=["no"])
        assert "Current status:" in out["console"]
        # The report is shown above the question.
        assert out["console"].index("Current status:") < out["console"].index(
            "would you like me to"
        )

    def test_input_module_never_receives_the_question(self):
        out = run([STATUS_PAYLOAD, "All done."], answers=["no"])
        for prompt in out["prompts"]:
            assert "would you like me to" not in prompt

    def test_the_prompt_is_a_short_prompt(self):
        out = run([STATUS_PAYLOAD, "All done."], answers=["no"])
        assert out["prompts"]
        assert all(len(prompt) < 40 for prompt in out["prompts"])


class TestTheEvent:
    """The event carries the question, the report travels in the context."""

    def test_question_not_answer(self):
        out = run([REPORT_PAYLOAD, "All done."], answers=["no"])
        assert out["events"], "no AgentQuestionEvent was produced"
        event = out["events"][0]
        assert len(event.question) < len(REPORT_PAYLOAD)
        assert event.question.startswith("Want me to start")
        assert event.context
        assert "Key findings" in event.context

    def test_the_input_type_follows_the_question(self):
        out = run([REPORT_PAYLOAD, "All done."], answers=["no"])
        event = out["events"][0]
        assert event.input_type == "yesno"


class TestPassword:
    """A password question is still shown to the operator."""

    def test_password_prompt_shows_the_question(self):
        out = run(["What is the sudo password?", "All done."], answers=["hunter2"])
        assert any("sudo password" in p for p in out["prompts"]) or (
            "sudo password" in out["console"]
        )

    def test_a_password_question_is_typed_as_such(self):
        out = run(["What is the sudo password?", "All done."], answers=["hunter2"])
        assert out["events"][0].input_type == "password"


class TestReAsk:
    """A rephrased question is not asked twice."""

    def test_a_rephrasing_is_not_asked_again(self):
        out = run(
            [
                "Shall I create the branch feature/sqitch-database-migrations?",
                "Should I create the branch feature/sqitch-database-migrations?",
                "All done.",
            ],
            answers=["no", "no"],
        )
        assert len(out["prompts"]) == 1

    def test_the_question_is_detected_once(self):
        out = run([STATUS_PAYLOAD, "All done."], answers=["no"])
        detected = [m for m in out["logs"] if "HITL question detected" in m]
        assert len(detected) == 1


class TestTimeout:
    """An empty answer is a timeout, not an explicit "no"."""

    def test_empty_answer_is_a_timeout(self):
        out = run([STATUS_PAYLOAD, "All done."], answers=[""])
        received = [m for m in out["logs"] if "HITL answer received" in m]
        assert received
        assert "timeout=True" in received[0]

    def test_an_explicit_no_is_not_a_timeout(self):
        out = run([STATUS_PAYLOAD, "All done."], answers=["no"])
        received = [m for m in out["logs"] if "HITL answer received" in m]
        assert received
        assert "timeout=False" in received[0]


class TestRoundTrip:
    """The answer still reaches the agent."""

    def test_answer_still_reaches_the_agent(self):
        out = run([STATUS_PAYLOAD, "All done."], answers=["no"])
        last_call = out["llm_calls"][-1]
        joined = " ".join(content for _, content in last_call)
        assert "Human response" in joined
        assert "no" in joined

    def test_a_free_form_answer_is_forwarded_verbatim(self):
        out = run(
            ["Shall I create the branch feature/x?", "All done."],
            answers=["yes, go ahead"],
        )
        last_call = out["llm_calls"][-1]
        joined = " ".join(content for _, content in last_call)
        assert "yes, go ahead" in joined


class TestMenu:
    """A question written as a list of choices wants a choice."""

    def test_a_list_question_is_typed_as_a_menu(self):
        out = run([STATUS_PAYLOAD, "All done."], answers=["1"])
        event = out["events"][0]
        assert event.input_type == "menu"
        assert event.options == [
            "Set up sqitch for database version control?",
            "Start with documentation for the sqitch integration?",
        ]

    def test_the_options_are_shown_once(self):
        out = run([STATUS_PAYLOAD, "All done."], answers=["1"])
        # The options travel with the question, which the consumer prints.
        assert "1. Set up sqitch for database version control?" in out["console"]
        # The input module only gets the short prompt.
        for prompt in out["prompts"]:
            assert "Set up sqitch" not in prompt
        assert out["prompts"]
        assert all(len(prompt) < 40 for prompt in out["prompts"])

    def test_the_choice_reaches_the_agent(self):
        out = run([STATUS_PAYLOAD, "All done."], answers=["2"])
        last_call = out["llm_calls"][-1]
        joined = " ".join(content for _, content in last_call)
        assert "Start with documentation for the sqitch integration?" in joined

    def test_an_empty_answer_selects_the_first_option(self):
        out = run([STATUS_PAYLOAD, "All done."], answers=[""])
        received = [m for m in out["logs"] if "HITL answer received" in m]
        assert received
        assert "timeout=True" in received[0]
        assert "Set up sqitch for database version control?" in received[0]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
