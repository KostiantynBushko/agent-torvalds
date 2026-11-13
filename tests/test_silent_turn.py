"""
Tests for the turn that says nothing.

A reasoning model can end its turn with a *thinking* and nothing else:
no text, and no tool call.  Nothing happened, and nothing was said.

The run used to end there.  The answer was built with ``str(result)``,
which returns the text of the model and nothing else, so the answer was
an empty string, and the operator was left with an empty box and no way
of telling that from a run that had never started.

The agent now gives the model one more turn, and the answer says plainly
that the model ended the turn without an answer.

Category: Infrastructure
"""

import asyncio
import importlib.util
import os
import sys
from pathlib import Path

import pytest
from llama_index.core.agent.workflow import AgentOutput
from llama_index.core.base.llms.types import (
    ChatMessage,
    ChatResponse,
    MessageRole,
    ThinkingBlock,
    ToolCallBlock,
)
from llama_index.core.bridge.pydantic import PrivateAttr
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.tools import FunctionTool
from llama_index.llms.ollama.base import Ollama

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent

from components.chat_message import to_answer_string
from components.hitl_agent import HITLFunctionAgent


def noop() -> str:
    """A tool that does nothing."""
    return "nothing to do"


class ScriptedOllama(Ollama):
    """An Ollama LLM that answers from a script and records every request.

    A step of the script is either a text — the answer of the model — or
    a pair ``("thinking", "...")``, which is a turn that carries a
    thinking and nothing else, or a triple ``("call", name, kwargs)``,
    which is a turn that acts.
    """

    _requests: list = PrivateAttr(default_factory=list)
    _script: list = PrivateAttr(default_factory=list)

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("model", "fake/model")
        kwargs.setdefault("base_url", "http://localhost:11434")
        super().__init__(*args, **kwargs)
        self._requests = []
        self._script = []

    @property
    def requests(self):
        return self._requests

    def set_script(self, script):
        self._script = list(script)

    def _next(self, messages):
        self._requests.append(list(messages))
        step = self._script.pop(0) if self._script else "The work is done."

        if isinstance(step, tuple) and step and step[0] == "thinking":
            return ChatResponse(
                message=ChatMessage(
                    role=MessageRole.ASSISTANT,
                    blocks=[ThinkingBlock(content=step[1])],
                )
            )

        if isinstance(step, tuple) and step and step[0] == "call":
            _, tool_name, tool_kwargs = step
            return ChatResponse(
                message=ChatMessage(
                    role=MessageRole.ASSISTANT,
                    blocks=[
                        ToolCallBlock(
                            tool_name=tool_name, tool_kwargs=tool_kwargs
                        )
                    ],
                )
            )

        return ChatResponse(
            message=ChatMessage(role=MessageRole.ASSISTANT, content=step)
        )

    async def astream_chat(self, messages, **kwargs):
        async def gen():
            yield self._next(list(messages))

        return gen()

    async def achat(self, messages, **kwargs):
        return self._next(list(messages))


@pytest.fixture
def llm():
    return ScriptedOllama()


@pytest.fixture
def memory():
    return ChatMemoryBuffer.from_defaults(token_limit=5000)


@pytest.fixture
def agent(llm, memory):
    agent = HITLFunctionAgent(
        tools=[FunctionTool.from_defaults(fn=noop, name="noop")],
        llm=llm,
        max_iterations=10,
        memory=memory,
        system_prompt="You are Torvalds.",
    )
    agent.hitl_enabled = False
    return agent


def _run(agent, llm, memory, request="fix the kconfig"):
    """Run the agent and return what the workflow answered."""
    async def _drive():
        handler = agent.run(request, memory=memory, max_iterations=10)
        try:
            return await handler
        except Exception:  # noqa: BLE001 - the run may end early
            return None

    return asyncio.run(_drive())


# ---------------------------------------------------------------------------
# The silent turn
# ---------------------------------------------------------------------------


class TestSilentTurn:
    """The turn that carries a thinking and nothing else."""

    def test_the_run_does_not_end_on_a_silent_turn(self, agent, llm, memory):
        """The model gets one more turn instead of ending the run."""
        llm.set_script(
            [("thinking", "Let me fix the kconfig."), "The fix is in."]
        )

        _run(agent, llm, memory)

        assert len(llm.requests) == 2, (
            "the agent ended the run on the silent turn — the model was "
            "never asked again"
        )

    def test_the_note_reaches_the_model(self, agent, llm, memory):
        """The second request says what went wrong."""
        llm.set_script(
            [("thinking", "Let me fix the kconfig."), "The fix is in."]
        )

        _run(agent, llm, memory)

        second = llm.requests[1]
        assert any(
            "empty" in str(message.content or "") for message in second
        ), "the model was not told that its last turn was empty"

    def test_the_run_ends_when_the_model_says_nothing_twice(
        self, agent, llm, memory
    ):
        """One more turn, not an endless one."""
        llm.set_script(
            [
                ("thinking", "Let me fix the kconfig."),
                ("thinking", "Let me fix the kconfig."),
            ]
        )

        result = _run(agent, llm, memory)

        assert len(llm.requests) == 2, (
            "the agent kept asking a model that says nothing"
        )
        assert "without an answer" in to_answer_string(result), (
            "the answer does not say that the model ended the turn without "
            "an answer"
        )

    def test_the_answer_carries_the_thinking_of_the_model(
        self, agent, llm, memory
    ):
        """The operator sees what the model was about to do."""
        llm.set_script(
            [
                ("thinking", "Let me fix the kconfig."),
                ("thinking", "Let me fix the kconfig."),
            ]
        )

        result = _run(agent, llm, memory)

        assert "Let me fix the kconfig." in to_answer_string(result)

    def test_an_answer_that_says_something_ends_the_run(
        self, agent, llm, memory
    ):
        """A normal answer is not given another turn."""
        llm.set_script(["The fix is in."])

        result = _run(agent, llm, memory)

        assert len(llm.requests) == 1
        assert "The fix is in." in to_answer_string(result)

    def test_a_turn_with_a_tool_call_is_not_silent(self, agent, llm, memory):
        """A turn that acts is not a turn that says nothing."""
        llm.set_script(
            [
                ("call", "noop", {}),
                "The work is done.",
            ]
        )

        _run(agent, llm, memory)

        assert len(llm.requests) >= 2, (
            "the agent ended the run on a turn that called a tool"
        )


# ---------------------------------------------------------------------------
# The answer the operator reads
# ---------------------------------------------------------------------------


class TestAnswerString:
    """The answer must never be an empty string."""

    def test_an_empty_answer_says_so(self):
        """An answer with nothing in it says that."""
        answer = to_answer_string(None)

        assert answer != ""
        assert "without an answer" in answer

    def test_a_thinking_is_shown_when_there_is_no_text(self):
        """The operator sees what the model was about to do."""
        message = ChatMessage(
            role=MessageRole.ASSISTANT,
            blocks=[ThinkingBlock(content="Let me fix the kconfig.")],
        )

        answer = to_answer_string(message)

        assert "without an answer" in answer
        assert "Let me fix the kconfig." in answer

    def test_the_text_wins_over_the_thinking(self):
        """An answer with text is the text of the model."""
        message = ChatMessage(role=MessageRole.ASSISTANT, content="The fix is in.")

        answer = to_answer_string(message)

        assert answer == "The fix is in."

    def test_a_plain_string_is_its_own_answer(self):
        """A string is the answer."""
        assert to_answer_string("The fix is in.") == "The fix is in."

    def test_a_mapping_is_unwrapped(self):
        """The answer of a mapping is the answer it carries."""
        message = ChatMessage(role=MessageRole.ASSISTANT, content="The fix is in.")

        assert to_answer_string({"response": message}) == "The fix is in."


# ---------------------------------------------------------------------------
# The console path
# ---------------------------------------------------------------------------


class _SilentConsumer:
    """An event consumer whose answer carries a thinking and nothing else."""

    def __init__(self, result):
        self.result = result

    def set_stats_handler(self, handler):
        self.stats_handler = handler

    def set_human_loop_handler(self, handler):
        self.human_loop_handler = handler

    async def consume_events(self, handler, user_msg):
        return self.result


class _Agent:
    """An agent whose workflow starts and returns a handler."""

    def run(self, *args, **kwargs):
        return object()


def _load_orchestrator(monkeypatch, name="agent-torvalds.py"):
    """Load a console orchestrator of the repository."""
    monkeypatch.setattr(sys, "argv", [name])
    spec = importlib.util.spec_from_file_location(
        "agent_torvalds_silent", ROOT / name
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _no_cache_writes(monkeypatch):
    """The test writes nothing into the cache of the operator."""
    monkeypatch.setattr(
        "agent_cache_system.increment_session_commands", lambda: None
    )


class TestConsolePath:
    """The console must never print an empty box."""

    @pytest.mark.asyncio
    async def test_a_silent_answer_reaches_the_screen(self, monkeypatch):
        """The operator sees what happened, not an empty box."""
        _no_cache_writes(monkeypatch)
        module = _load_orchestrator(monkeypatch)

        message = ChatMessage(
            role=MessageRole.ASSISTANT,
            blocks=[ThinkingBlock(content="Let me fix the kconfig.")],
        )
        result = AgentOutput(
            response=message, tool_calls=[], current_agent_name="agent"
        )
        consumer = _SilentConsumer(result)

        response, _stats = await module.prompt_handler(
            "fix the kconfig",
            _Agent(),
            enable_stats=False,
            event_consumer=consumer,
        )

        assert response.strip() != "", (
            "the console printed nothing at all — the operator cannot tell "
            "that from a run that never started"
        )
        assert "without an answer" in response
        assert "Let me fix the kconfig." in response

    @pytest.mark.asyncio
    async def test_an_answer_with_text_is_printed_unchanged(self, monkeypatch):
        """A normal answer is the text of the model."""
        _no_cache_writes(monkeypatch)
        module = _load_orchestrator(monkeypatch)

        message = ChatMessage(
            role=MessageRole.ASSISTANT, content="The fix is in."
        )
        result = AgentOutput(
            response=message, tool_calls=[], current_agent_name="agent"
        )
        consumer = _SilentConsumer(result)

        response, _stats = await module.prompt_handler(
            "fix the kconfig",
            _Agent(),
            enable_stats=False,
            event_consumer=consumer,
        )

        assert response == "The fix is in."
