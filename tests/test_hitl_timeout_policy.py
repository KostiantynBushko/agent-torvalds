"""Regression tests for the HITL timeout policy.

The operator's rule (2026-10-22):

    "if timeout is -1 you have to stop and wait; if timeout is set you
     have to wait and timeout expires you can act on your own judgement"

Defect **D16**: when the timeout expired, the model was fed the fallback
answer as if the human had said it.  With the shipped default (no fallback
answer) it was fed an *empty* turn, which for a yes/no question is
indistinguishable from a "no" — so the agent refused to act, the exact
opposite of the rule.

These tests drive the **real** stack: the real ``HITLFunctionAgent``, the
real ``EventConsumer`` and the real ``ConsoleInputModule``.  Only the human
is a double.
"""
import asyncio
import builtins
import os
import sys
import time
from typing import Any, List, Optional, Sequence

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llama_index.core.base.llms.types import ChatMessage, ChatResponse
from llama_index.core.llms.callbacks import llm_chat_callback
from llama_index.core.llms.mock import MockFunctionCallingLLM
from llama_index.core.tools import FunctionTool
from pydantic import Field
from rich.console import Console

from components.event_consumer import EventConsumer
from components.hitl_agent import HITLFunctionAgent
from components.human_loop_handler import HumanLoopHandler
from components.spinner_controller import SpinnerController
from components.state_handler import StateHandler

QUESTION = "Which one should I use?"
YES_NO_QUESTION = "Shall I delete the database?"


def add_two(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


class QuestionLLM(MockFunctionCallingLLM):
    """Asks the question first, then answers with a final message.

    The second call carries the messages the model was given about the
    human's answer — that is what these tests look at.
    """

    calls: List[Any] = Field(default_factory=list)
    question: str = QUESTION

    @llm_chat_callback()
    async def astream_chat(self, messages: Sequence[ChatMessage], **kwargs: Any):
        self.calls.append([(m.role, str(m.content)) for m in messages])
        text = self.question if len(self.calls) == 1 else "Understood."

        async def gen():
            yield ChatResponse(
                message=ChatMessage(role="assistant", content=text),
                delta=text,
                raw={"message": {"role": "assistant", "content": text}},
            )

        return gen()


class Human:
    """The human at the keyboard: answers late, or never."""

    def __init__(self, delay: Optional[float], answer: str = "2") -> None:
        self.delay = delay
        self.answer = answer
        self.prompts: List[str] = []

    def input(self, message: str = "") -> str:
        self.prompts.append(message)
        if self.delay is None:
            time.sleep(30)
        time.sleep(self.delay)
        return self.answer


async def _run(
    timeout: int,
    human: Human,
    default_answer: str = "1",
    question: str = QUESTION,
    wait_for: Optional[float] = None,
) -> dict:
    """Run one request through the real agent + consumer + input module."""
    handler = HumanLoopHandler(enable_hitl=True, default_timeout=timeout)
    console = Console(force_terminal=False, width=80)
    consumer = EventConsumer(
        spinner_controller=SpinnerController(console=console),
        state_handler=StateHandler(),
        console=console,
        hitl_timeout=timeout,
        hitl_default_answer=default_answer,
        hitl_enabled=True,
        human_loop_handler=handler,
    )

    llm = QuestionLLM(question=question)
    agent = HITLFunctionAgent(
        tools=[FunctionTool.from_defaults(fn=add_two)],
        llm=llm,
        hitl_enabled=True,
        hitl_default_timeout=timeout,
        hitl_default_answer=default_answer,
    )

    original_input = builtins.input
    builtins.input = human.input
    try:
        workflow = agent.run("pick one")
        coro = consumer.consume_events(workflow, "pick one")
        if wait_for is None:
            await coro
            completed = True
        else:
            try:
                await asyncio.wait_for(coro, timeout=wait_for)
                completed = True
            except asyncio.TimeoutError:
                completed = False
    finally:
        builtins.input = original_input

    return {
        "completed": completed,
        "llm_calls": llm.calls,
        "prompts": human.prompts,
        "timeout_log": handler.get_timeout_log(),
    }


def _model_saw(result: dict) -> str:
    """Return what the model was told in its last call."""
    calls = result["llm_calls"]
    if not calls:
        return ""
    return " ".join(content for _role, content in calls[-1])


class TestTimeoutPolicy:
    """The operator's rule, against the real stack."""

    def test_no_timeout_waits_for_a_slow_human(self):
        result = _run_sync(timeout=-1, human=Human(delay=1.0))
        assert result["completed"]
        assert "2" in _model_saw(result)

    def test_no_timeout_waits_for_a_silent_human(self):
        """With -1 the agent must stop and wait — it must not decide alone."""
        result = _run_sync(timeout=-1, human=Human(delay=None), wait_for=2.0)
        assert not result["completed"]
        assert not result["timeout_log"]

    def test_a_finite_timeout_expires_and_the_agent_carries_on(self):
        result = _run_sync(timeout=1, human=Human(delay=5.0), default_answer="1")
        assert result["completed"]
        assert result["timeout_log"], "the timeout must be recorded"

    def test_the_model_is_told_that_nobody_answered(self):
        """D16: the fallback answer must not look like the human's answer."""
        result = _run_sync(timeout=1, human=Human(delay=5.0), default_answer="1")
        told = _model_saw(result)
        assert "did not answer" not in told  # sanity: the wording changed
        assert "No human response" in told
        assert "own judgement" in told

    def test_the_model_is_told_even_without_a_fallback_answer(self):
        """The shipped default is an empty fallback — the worst case."""
        result = _run_sync(
            timeout=1,
            human=Human(delay=5.0),
            default_answer="",
            question=YES_NO_QUESTION,
        )
        told = _model_saw(result)
        assert "No human response" in told
        # An empty human turn would be read as a "no".
        assert "[Human response] " not in told

    def test_a_real_answer_is_still_reported_as_an_answer(self):
        """The fix must not touch the normal path."""
        result = _run_sync(timeout=-1, human=Human(delay=0.1))
        told = _model_saw(result)
        assert "[Human response] 2" in told
        assert "No human response" not in told


def _run_sync(*args, **kwargs) -> dict:
    """Run the async scenario and return its result."""
    async def _go() -> dict:
        return await _run(*args, **kwargs)

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_go())
    finally:
        loop.close()
