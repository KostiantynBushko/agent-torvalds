"""
The size of the prompt that goes to the model.

The operator asked on 2026-11-04:

    *"I need to see in the log the context size in tokens and size of
    bytes.  So when request is made to LLM I want to see current context
    size"*

These tests cover the measurement itself and the line the agent writes
before every request to the model.

Category: Infrastructure
"""

import logging

import pytest
from llama_index.core.base.llms.types import (
    ChatMessage,
    ChatResponse,
    MessageRole,
    ToolCallBlock,
)
from llama_index.core.bridge.pydantic import PrivateAttr
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.tools import FunctionTool
from llama_index.llms.ollama.base import Ollama

from components.context_metrics import (
    ContextSize,
    count_tokens_of,
    describe_context,
    measure_context,
    prompt_text,
    tool_schema_text,
)
from components.hitl_agent import HITLFunctionAgent


# ---------------------------------------------------------------------------
# The measurement
# ---------------------------------------------------------------------------


def test_the_tokens_of_the_prompt_are_counted():
    """The messages of the prompt are counted with the agent's tokenizer."""
    messages = [
        ChatMessage(role=MessageRole.SYSTEM, content="You are Torvalds."),
        ChatMessage(role=MessageRole.USER, content="How much disk is left?"),
    ]

    size = measure_context(messages)

    assert size.messages == 2
    assert size.tokens > 0
    assert not size.estimated


def test_the_bytes_of_the_prompt_are_counted_in_utf8():
    """A non-ASCII character costs more than one byte."""
    ascii_message = ChatMessage(role=MessageRole.USER, content="a" * 10)
    unicode_message = ChatMessage(role=MessageRole.USER, content="а" * 10)

    ascii_size = measure_context([ascii_message])
    unicode_size = measure_context([unicode_message])

    assert ascii_size.bytes == 10
    # The Cyrillic "а" takes two bytes in UTF-8.
    assert unicode_size.bytes == 20


def test_the_tool_schemas_are_counted_separately():
    """The schemas travel with every request, but they are no messages."""
    tool = FunctionTool.from_defaults(
        fn=lambda path: path,
        name="read_file",
        description="Read a file from the disk.",
    )
    messages = [ChatMessage(role=MessageRole.USER, content="read the file")]

    size = measure_context(messages, tools=[tool])

    assert size.messages == 1
    assert size.tool_schema_tokens > 0
    assert size.tool_schema_bytes > 0
    assert size.total_tokens == size.tokens + size.tool_schema_tokens
    assert size.total_bytes == size.bytes + size.tool_schema_bytes


def test_a_tool_call_is_part_of_the_size_of_the_prompt():
    """The name of the tool and its arguments take up prompt space."""
    plain = ChatMessage(role=MessageRole.ASSISTANT, content="working on it")
    calling = ChatMessage(
        role=MessageRole.ASSISTANT,
        blocks=[
            ToolCallBlock(
                tool_name="read_xlsx_file",
                tool_kwargs={"path": "shtab.xlsx"},
            )
        ],
    )

    assert measure_context([calling]).tokens > measure_context([plain]).tokens


def test_the_text_of_the_prompt_holds_the_tool_calls():
    """The text of the prompt is what the tokenizer is given."""
    message = ChatMessage(
        role=MessageRole.ASSISTANT,
        blocks=[
            ToolCallBlock(tool_name="pwd", tool_kwargs={"path": "/"}),
        ],
    )

    text = prompt_text([message])

    assert "pwd" in text
    assert "/" in text


def test_the_tool_schemas_are_empty_without_tools():
    """No tools, no schemas."""
    assert tool_schema_text(None) == ""
    assert tool_schema_text([]) == ""


def test_an_empty_prompt_is_measured():
    """An empty prompt is not an error."""
    size = measure_context([])

    assert size.messages == 0
    assert size.tokens == 0
    assert size.bytes == 0
    assert size.total_tokens == 0


def test_the_tokens_are_estimated_when_there_is_no_tokenizer():
    """A tokenizer that cannot be loaded degrades into an estimate."""
    def broken(_text):
        raise RuntimeError("no tokenizer here")

    tokens, estimated = count_tokens_of("some text", broken)

    assert estimated is True
    assert tokens > 0


def test_the_measurement_survives_a_broken_tokenizer():
    """The bytes are exact even when the tokens are only estimated."""
    def broken(_text):
        raise RuntimeError("no tokenizer here")

    size = measure_context(
        [ChatMessage(role=MessageRole.USER, content="hello")],
        tokenizer=broken,
    )

    assert size.estimated is True
    assert size.bytes == 5


# ---------------------------------------------------------------------------
# The description
# ---------------------------------------------------------------------------


def test_the_description_carries_the_size_and_the_share_of_the_window():
    """The line the operator reads carries the numbers that matter."""
    size = ContextSize(
        messages=12,
        tokens=1000,
        bytes=4096,
        tool_schema_tokens=200,
        tool_schema_bytes=512,
    )

    text = describe_context(size, window=8192)

    assert "12 messages" in text
    assert "1,200 tokens" in text
    assert "4.5 KB" in text
    assert "14.6% of the 8,192-token window" in text


def test_the_description_of_one_message_is_singular():
    """One message is not "1 messages"."""
    text = describe_context(ContextSize(messages=1))

    assert "1 message," in text


def test_the_description_says_that_the_tokens_are_estimated():
    """An estimate must not be read as a count."""
    text = describe_context(ContextSize(messages=1, tokens=10, estimated=True))

    assert "estimated" in text


# ---------------------------------------------------------------------------
# The line in the log
# ---------------------------------------------------------------------------


class FakeOllama(Ollama):
    """An Ollama LLM that answers from a script and records every request."""

    _requests: list = PrivateAttr(default_factory=list)
    _script: list = PrivateAttr(default_factory=list)

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("model", "fake/model")
        kwargs.setdefault("base_url", "http://localhost:11434")
        kwargs.setdefault("context_window", 8192)
        super().__init__(*args, **kwargs)
        self._requests = []
        self._script = []

    @property
    def requests(self):
        return self._requests

    def set_script(self, script):
        self._script = list(script)

    def get_context_window(self) -> int:
        return 8192

    def _next(self, messages):
        self._requests.append(list(messages))
        if not self._script:
            return ChatResponse(
                message=ChatMessage(role=MessageRole.ASSISTANT, content="Done.")
            )
        step = self._script.pop(0)
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


def _build_agent():
    llm = FakeOllama()
    tools = [
        FunctionTool.from_defaults(
            fn=lambda path: "content",
            name="read_file",
            description="Read a file from the disk.",
        )
    ]
    memory = ChatMemoryBuffer.from_defaults(token_limit=5000)
    agent = HITLFunctionAgent(
        tools=tools,
        llm=llm,
        max_iterations=10,
        memory=memory,
        system_prompt="You are Torvalds.",
    )
    agent.hitl_enabled = False
    return agent, llm, memory


def _run(agent, llm, memory, request, script):
    """Run the agent and return the recorded requests."""
    import asyncio

    llm.set_script(script)
    memory.put(ChatMessage(content="CONTEXT: ### Registered Projects\n- a project"))

    async def _drive():
        handler = agent.run(request, memory=memory, max_iterations=10)
        try:
            await handler
        except Exception:  # noqa: BLE001 - the run may end early
            pass

    asyncio.run(_drive())
    return llm.requests


def _context_lines(caplog):
    """The lines the agent wrote about the size of the prompt."""
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == "components.hitl_agent"
        and record.getMessage().startswith("Context: ")
    ]


def test_the_size_of_the_prompt_is_logged_with_every_request(caplog):
    """Every request to the model is preceded by the size of its prompt."""
    agent, llm, memory = _build_agent()

    with caplog.at_level(logging.INFO, logger="components.hitl_agent"):
        requests = _run(agent, llm, memory, "how much disk is left?", ["Done."])

    lines = _context_lines(caplog)

    assert requests, "the agent never called the model"
    assert len(lines) == len(requests), (
        f"the agent made {len(requests)} requests but logged {len(lines)} "
        f"context lines"
    )


def test_the_logged_line_carries_the_tokens_and_the_bytes(caplog):
    """The line carries the numbers the operator asked for."""
    agent, llm, memory = _build_agent()

    with caplog.at_level(logging.INFO, logger="components.hitl_agent"):
        _run(agent, llm, memory, "how much disk is left?", ["Done."])

    line = _context_lines(caplog)[0]

    assert "tokens" in line
    assert "KB" in line or "B" in line
    assert "messages" in line
    assert "of the 8,192-token window" in line


def test_the_size_grows_with_the_scratchpad(caplog):
    """A run with tool calls makes the prompt grow, and the log shows it."""
    agent, llm, memory = _build_agent()

    with caplog.at_level(logging.INFO, logger="components.hitl_agent"):
        _run(
            agent,
            llm,
            memory,
            "read the file",
            [("call", "read_file", {"path": "a.txt"})] * 3,
        )

    lines = _context_lines(caplog)

    assert len(lines) >= 2
    # The last prompt carries the turns of the run, so it is bigger than
    # the first one.
    def tokens_of(line):
        return int(line.split(",")[1].split()[0].replace(",", ""))

    assert tokens_of(lines[-1]) > tokens_of(lines[0])


def test_the_logging_can_be_turned_off(caplog):
    """The operator may not want the line in the log."""
    agent, llm, memory = _build_agent()
    agent.context_logging_enabled = False

    with caplog.at_level(logging.INFO, logger="components.hitl_agent"):
        requests = _run(agent, llm, memory, "how much disk is left?", ["Done."])

    assert requests, "the agent never called the model"
    assert _context_lines(caplog) == []


def test_the_size_is_logged_when_the_guard_stands_down(caplog):
    """The guard is off by default, and the size is logged anyway."""
    agent, llm, memory = _build_agent()
    agent.context_guard_enabled = False

    with caplog.at_level(logging.INFO, logger="components.hitl_agent"):
        _run(agent, llm, memory, "how much disk is left?", ["Done."])

    assert _context_lines(caplog)


def test_the_size_is_logged_when_the_guard_trims_the_prompt(caplog):
    """The guard does not change what is measured: the prompt that is sent."""
    agent, llm, memory = _build_agent()
    agent.context_guard_enabled = True

    with caplog.at_level(logging.INFO, logger="components.hitl_agent"):
        requests = _run(
            agent,
            llm,
            memory,
            "how much disk is left?",
            [("call", "read_file", {"path": "a.txt"})] * 3,
        )

    lines = _context_lines(caplog)

    assert requests
    assert len(lines) == len(requests)


def test_the_logged_size_matches_the_prompt_that_was_sent(caplog):
    """The number in the log is the number of the prompt on the wire."""
    from components.context_metrics import measure_context as measure

    agent, llm, memory = _build_agent()

    with caplog.at_level(logging.INFO, logger="components.hitl_agent"):
        requests = _run(agent, llm, memory, "how much disk is left?", ["Done."])

    lines = _context_lines(caplog)
    sent = requests[0]

    size = measure(sent, tools=agent.tools, tokenizer=agent._safe_tokenizer())
    logged_tokens = int(lines[0].split(",")[1].split()[0].replace(",", ""))

    assert logged_tokens == size.total_tokens
