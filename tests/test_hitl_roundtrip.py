"""
Regression tests for the Human-in-the-Loop round-trip.

These tests cover the defects found in ``investigate/hitl-investigate/``:

  #1  ``_extract_text()`` could not read a ``ChatResponse`` — the text lives
      in ``response.message.content``.
  #2  ``CBEventType.AGENT_STEP`` is never emitted, so the ``on_event_start``
      branch was dead code.
  #3  ``AgentQuestionEvent`` sent with ``ctx.send_event()`` never reached the
      event stream (and external code cannot call ``write_event_to_stream``).
  #4  No workflow step accepted ``AgentAnswerEvent``, so the answer could
      never reach the agent.
  #5  The callback path *and* the stream path both prompted — a double
      prompt.
  #6  ``--hitl-default-answer`` never reached the ``HumanLoopHandler``.

The mock LLM mirrors the **real Ollama** payload shape
(``raw={"message": {"content": ...}}``) so the tests cannot pass by accident
against a mock whose shape the broken extractor would have handled.
"""
import asyncio
import sys
import os
from typing import Any, List, Sequence

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llama_index.core.base.llms.types import ChatMessage, ChatResponse
from llama_index.core.llms.callbacks import llm_chat_callback
from llama_index.core.llms.mock import MockFunctionCallingLLM
from llama_index.core.tools import FunctionTool
from pydantic import Field

from components.event_consumer import EventConsumer
from components.hitl_agent import HITLFunctionAgent, extract_text, is_question
from components.hitl_events import AgentAnswerEvent, AgentQuestionEvent
from components.human_loop_handler import HumanLoopHandler
from components.spinner_controller import SpinnerController
from components.state_handler import StateHandler
from rich.console import Console

QUESTION = "Shall I delete the database?"
FINAL = "Understood, I will not delete it."


def add_two(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


class OllamaShapeLLM(MockFunctionCallingLLM):
    """Answers with a question first, then with a final message.

    The ``raw`` payload mirrors the real Ollama shape, so a test written
    against a mock with ``raw={"content": ...}`` cannot pass by accident.
    """

    calls: List[Any] = Field(default_factory=list)

    @llm_chat_callback()
    async def astream_chat(self, messages: Sequence[ChatMessage], **kwargs: Any):
        self.calls.append([(m.role, str(m.content)) for m in messages])
        text = QUESTION if len(self.calls) == 1 else FINAL

        async def gen():
            yield ChatResponse(
                message=ChatMessage(role="assistant", content=text),
                delta=text,
                raw={"message": {"role": "assistant", "content": text}},
            )

        return gen()


class RecordingInput:
    """Stand-in for the console input module that records the prompts."""

    def __init__(self, answer: str = "no") -> None:
        self.answer = answer
        self.prompts: List[str] = []

    async def prompt(self, message: str = "", default: str = "", timeout: int = 30) -> str:
        self.prompts.append(message)
        return self.answer

    async def confirm(self, message: str = "", default_yes: bool = True, timeout: int = 30) -> bool:
        self.prompts.append(message)
        return self.answer.strip().lower() in ("y", "yes")

    async def menu(self, message: str = "", options: List[str] = None, timeout: int = 30) -> str:
        self.prompts.append(message)
        return (options or [""])[0]

    async def password(self, message: str = "", timeout: int = 30) -> str:
        self.prompts.append(message)
        return self.answer


def _make_consumer(handler: HumanLoopHandler, hitl_enabled: bool = True) -> EventConsumer:
    console = Console(force_terminal=False, width=80)
    return EventConsumer(
        spinner_controller=SpinnerController(console=console),
        state_handler=StateHandler(),
        console=console,
        hitl_timeout=5,
        hitl_default_answer="no",
        hitl_enabled=hitl_enabled,
        human_loop_handler=handler,
    )


async def _run_async(answer: str = "no", hitl_enabled: bool = True) -> dict:
    """Run one request through the real consumer + HITL agent."""
    handler = HumanLoopHandler(enable_hitl=hitl_enabled)
    consumer = _make_consumer(handler, hitl_enabled=hitl_enabled)
    recorder = RecordingInput(answer)
    consumer.console_input = recorder

    llm = OllamaShapeLLM()
    agent = HITLFunctionAgent(
        tools=[FunctionTool.from_defaults(fn=add_two)],
        llm=llm,
        hitl_enabled=hitl_enabled,
        hitl_default_timeout=5,
        hitl_default_answer="no",
    )

    workflow_handler = agent.run("delete the database")
    result = await consumer.consume_events(workflow_handler, "delete the database")

    return {
        "prompts": recorder.prompts,
        "llm_calls": llm.calls,
        "result": result,
        "consumer": consumer,
        "handler": handler,
    }


def _run(answer: str = "no", hitl_enabled: bool = True) -> dict:
    """Synchronous wrapper around :func:`_run_async`."""
    return asyncio.run(_run_async(answer=answer, hitl_enabled=hitl_enabled))


# ---------------------------------------------------------------------------
# Defect #1 — text extraction
# ---------------------------------------------------------------------------

class TestExtractText:
    """The extractor must read the assistant text from a ChatResponse."""

    def test_chat_response_ollama_shape(self):
        response = ChatResponse(
            message=ChatMessage(role="assistant", content=QUESTION),
            raw={"message": {"role": "assistant", "content": QUESTION}},
        )
        assert extract_text(response) == QUESTION
        assert is_question(extract_text(response)) is True

    def test_chat_response_mock_shape(self):
        response = ChatResponse(
            message=ChatMessage(role="assistant", content=QUESTION),
            raw={"content": QUESTION},
        )
        assert extract_text(response) == QUESTION

    def test_chat_message(self):
        assert extract_text(ChatMessage(role="assistant", content=QUESTION)) == QUESTION

    def test_plain_string(self):
        assert extract_text(QUESTION) == QUESTION

    def test_none(self):
        assert extract_text(None) == ""

    def test_handler_extractor_matches(self):
        handler = HumanLoopHandler()
        response = ChatResponse(
            message=ChatMessage(role="assistant", content=QUESTION),
            raw={"message": {"role": "assistant", "content": QUESTION}},
        )
        assert handler._extract_text(response) == QUESTION


# ---------------------------------------------------------------------------
# Defect #2 — the dead AGENT_STEP branch
# ---------------------------------------------------------------------------

class TestNoDeadAgentStepBranch:
    """``CBEventType.AGENT_STEP`` is never emitted by llama-index."""

    def test_agent_step_start_is_inert(self):
        from llama_index.core.callbacks.schema import CBEventType, EventPayload

        handler = HumanLoopHandler()
        before = len(handler.get_question_history())
        handler.on_event_start(
            event_type=CBEventType.AGENT_STEP,
            payload={EventPayload.COMPLETION: "Do you want to proceed?"},
            event_id="e1",
        )
        assert len(handler.get_question_history()) == before

    def test_llm_end_records_the_question(self):
        from llama_index.core.callbacks.schema import CBEventType, EventPayload

        handler = HumanLoopHandler()
        response = ChatResponse(
            message=ChatMessage(role="assistant", content="Do you want to proceed?"),
            raw={"message": {"role": "assistant", "content": "Do you want to proceed?"}},
        )
        handler.on_event_end(
            event_type=CBEventType.LLM,
            payload={EventPayload.RESPONSE: response},
            event_id="e1",
        )
        assert len(handler.get_question_history()) == 1


# ---------------------------------------------------------------------------
# Defects #3 and #4 — the question reaches the consumer, the answer the agent
# ---------------------------------------------------------------------------

class TestRoundTrip:
    """The full round-trip through the real event stream."""

    def test_question_reaches_the_consumer(self):
        out = _run()
        assert out["consumer"].get_hitl_stats()["question_count"] == 1

    def test_answer_reaches_the_agent(self):
        out = _run(answer="no")
        last_call = out["llm_calls"][-1]
        joined = " ".join(content for _, content in last_call)
        assert "Human response" in joined
        assert "no" in joined

    def test_final_answer_reflects_the_human(self):
        out = _run(answer="no")
        assert "not delete" in str(out["result"]).lower()

    def test_affirmative_answer_is_forwarded(self):
        out = _run(answer="yes, go ahead")
        joined = " ".join(c for _, c in out["llm_calls"][-1])
        assert "yes, go ahead" in joined


# ---------------------------------------------------------------------------
# Defect #5 — exactly one prompt
# ---------------------------------------------------------------------------

class TestSinglePrompt:
    """One question must produce exactly one prompt."""

    def test_exactly_one_prompt(self):
        out = _run()
        assert len(out["prompts"]) == 1

    def test_the_handler_has_no_prompting_path(self):
        """The callback handler must not prompt.

        The handler used to prompt as well, which produced two prompts for
        one question as soon as detection started working.  The prompt now
        lives exclusively in the ``EventConsumer``.
        """
        handler = HumanLoopHandler()
        for attr in ("_prompt_user", "_handle_question", "_console_prompt",
                     "_whiptail_prompt"):
            assert not hasattr(handler, attr), (
                f"HumanLoopHandler must not own the prompting path ({attr})"
            )


# ---------------------------------------------------------------------------
# Defect #6 — the default answer reaches the handler
# ---------------------------------------------------------------------------

class TestDefaultAnswerPropagation:
    """``--hitl-default-answer`` must reach the handler and the agent."""

    def test_handler_default_answer(self):
        handler = HumanLoopHandler(default_answer="fallback")
        assert handler.default_answer == "fallback"

    def test_agent_default_answer(self):
        agent = HITLFunctionAgent(
            tools=[], llm=OllamaShapeLLM(), hitl_default_answer="fallback"
        )
        assert agent.hitl_default_answer == "fallback"

    def test_timeout_uses_the_default_answer(self):
        handler = HumanLoopHandler(default_answer="fallback")
        consumer = _make_consumer(handler)
        consumer.hitl_default_answer = "fallback"

        recorder = RecordingInput("")  # the user does not answer
        consumer.console_input = recorder

        event = AgentQuestionEvent(
            question="Do you want to proceed?",
            question_id="q-timeout",
            timeout=5,
            default_answer="fallback",
        )

        mock_handler = _MockHandler()
        consumer._current_handler = mock_handler

        asyncio.run(consumer._on_agent_question(event))

        sent = mock_handler.sent[0]
        assert sent.answer == "fallback"
        assert sent.was_timeout is True

        # The timeout is logged in the history.
        assert len(handler.get_timeout_log()) == 1


class _MockHandler:
    """Minimal stand-in for the workflow handler."""

    def __init__(self) -> None:
        self.sent: List[Any] = []
        self.ctx = self

    def send_event(self, event: Any) -> None:
        self.sent.append(event)


# ---------------------------------------------------------------------------
# Regression — HITL disabled changes nothing
# ---------------------------------------------------------------------------

class TestHitlDisabled:
    """With HITL off the agent behaves like a plain FunctionAgent."""

    def test_no_prompt(self):
        out = _run(hitl_enabled=False)
        assert len(out["prompts"]) == 0

    def test_single_llm_call(self):
        out = _run(hitl_enabled=False)
        assert len(out["llm_calls"]) == 1


# ---------------------------------------------------------------------------
# Event hierarchy — the framework contract
# ---------------------------------------------------------------------------

class TestEventHierarchy:
    """The HITL events must subclass the framework HITL events."""

    def test_question_is_an_input_required_event(self):
        from workflows.events import InputRequiredEvent

        event = AgentQuestionEvent(question="q?", question_id="q1")
        assert isinstance(event, InputRequiredEvent)

    def test_answer_is_a_human_response_event(self):
        from workflows.events import HumanResponseEvent

        event = AgentAnswerEvent(question_id="q1", answer="yes")
        assert isinstance(event, HumanResponseEvent)

    def test_answer_mirrors_the_response_field(self):
        event = AgentAnswerEvent(question_id="q1", answer="yes")
        assert event.response == "yes"
