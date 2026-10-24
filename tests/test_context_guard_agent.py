"""
Integration tests for the context guard inside the agent.

These drive the real ``HITLFunctionAgent`` workflow with a mock LLM, so the
message lists that would be sent to the model are the real ones.

Category: Infrastructure
"""

import json

import pytest
from llama_index.core.base.llms.types import ChatMessage, ChatResponse, MessageRole
from llama_index.core.bridge.pydantic import PrivateAttr
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.tools import FunctionTool
from llama_index.llms.ollama.base import Ollama

from components.context_guard import count_tokens, has_user_query
from components.hitl_agent import HITLFunctionAgent


class FakeOllama(Ollama):
    """An Ollama LLM that answers from a script and records every request."""

    _requests: list = PrivateAttr(default_factory=list)
    _script: list = PrivateAttr(default_factory=list)
    _context_window: int = PrivateAttr(default=8192)

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

    def get_context_window(self) -> int:
        return self._context_window

    def _next(self, messages):
        self._requests.append(list(messages))
        if not self._script:
            return ChatResponse(
                message=ChatMessage(role=MessageRole.ASSISTANT, content="Done.")
            )
        step = self._script.pop(0)
        return ChatResponse(
            message=ChatMessage(role=MessageRole.ASSISTANT, content=step)
        )

    async def astream_chat(self, messages, **kwargs):
        async def gen():
            yield self._next(list(messages))

        return gen()

    async def achat(self, messages, **kwargs):
        return self._next(list(messages))


def huge_tool(path: str) -> str:
    """A tool that returns a very large payload, like reading a spreadsheet."""
    return "\n".join(
        f"row {i} | 1234567890 | 3400,00 | ХАРКІВ | 2026-10-01" for i in range(4000)
    )


@pytest.fixture
def agent_and_llm():
    llm = FakeOllama()
    tools = [
        FunctionTool.from_defaults(
            fn=huge_tool,
            name="read_xlsx_file",
            description="Read data from an Excel .xlsx file.",
        )
    ]
    memory = ChatMemoryBuffer.from_defaults(token_limit=5000)
    agent = HITLFunctionAgent(
        tools=tools,
        llm=llm,
        max_iterations=30,
        memory=memory,
        system_prompt="You are Torvalds.",
    )
    agent.hitl_enabled = False
    return agent, llm, memory


def _run(agent, llm, memory, request, script):
    """Run the agent and return the recorded requests.

    The run may end early (the model may stop calling tools); that is not
    a failure for these tests.
    """
    import asyncio

    llm.set_script(script)
    memory.put(ChatMessage(content="CONTEXT: ### Registered Projects\n- mytlushko"))

    async def _drive():
        handler = agent.run(request, memory=memory, max_iterations=30)
        try:
            await handler
        except Exception:  # noqa: BLE001 - the run may end early
            pass

    asyncio.run(_drive())
    return llm.requests


def test_agent_keeps_the_prompt_within_the_context_window(agent_and_llm):
    """The prompt sent to the model must never exceed the context window."""
    agent, llm, memory = agent_and_llm
    request = "merge the entities of column D into shtab.xlsx"

    # Every step produces a tool result of roughly 4000 rows, which is far
    # more than the 8192-token window can hold.
    script = [""] * 25
    requests = _run(agent, llm, memory, request, script)

    assert requests, "the agent never called the model"

    for index, messages in enumerate(requests):
        tokens = count_tokens(messages)
        assert tokens <= 8192, (
            f"call {index} sent {tokens} tokens, which is more than the "
            f"8192-token context window"
        )
        assert has_user_query(messages), (
            f"call {index} has no user query — the model template would "
            f"reject it"
        )


def test_agent_keeps_the_user_request_in_every_prompt(agent_and_llm):
    agent, llm, memory = agent_and_llm
    request = "merge the entities of column D into shtab.xlsx"

    requests = _run(agent, llm, memory, request, [""] * 25)

    for index, messages in enumerate(requests):
        texts = [m.content or "" for m in messages if m.role == MessageRole.USER]
        assert any(request in text for text in texts), (
            f"call {index} lost the user request"
        )


def test_agent_restores_the_request_when_the_memory_dropped_it(agent_and_llm):
    """A memory that trimmed the request away must not break the run."""
    agent, llm, memory = agent_and_llm
    request = "merge the entities of column D into shtab.xlsx"

    # A memory that only holds an assistant turn: no user query at all.
    memory.put(ChatMessage(role=MessageRole.ASSISTANT, content="earlier answer"))
    requests = _run(agent, llm, memory, request, [""] * 5)

    assert requests
    for index, messages in enumerate(requests):
        assert has_user_query(messages), f"call {index} has no user query"
        texts = [m.content or "" for m in messages if m.role == MessageRole.USER]
        assert any(request in text for text in texts), (
            f"call {index} did not restore the user request"
        )
