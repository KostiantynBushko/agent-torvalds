"""
Unit tests for the readable rendering of a chat message.

Tests:
- to_string() — one message, in every shape it can take (text,
  thinking, a tool call as a block, a tool call in additional_kwargs,
  an image, an empty message).
- to_strings() — a prompt, one line per message.
- EventConsumer._on_agent_input() — the integration: the debug log
  carries the readable prompt and not the repr, and the state holds
  the readable text.

Run with:
    pytest tests/test_chat_message.py -v
"""
import logging
import os
import sys

import pytest
from unittest.mock import Mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llama_index.core.base.llms.types import (
    ChatMessage,
    ImageBlock,
    MessageRole,
    ThinkingBlock,
    ToolCallBlock,
)

from components.chat_message import to_string, to_strings
from components.event_consumer import EventConsumer
from components.spinner_controller import SpinnerController
from components.state_handler import StateHandler
from rich.console import Console


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def consumer() -> EventConsumer:
    """An EventConsumer with a real spinner, state handler and console."""
    console = Console(force_terminal=True, width=80)
    return EventConsumer(
        spinner_controller=SpinnerController(console=console),
        state_handler=StateHandler(),
        console=console,
    )


@pytest.fixture
def prompt() -> list:
    """A small but realistic prompt."""
    return [
        ChatMessage(
            role=MessageRole.SYSTEM,
            content="You are Torvalds, a technical AI assistant.",
        ),
        ChatMessage(
            role=MessageRole.USER,
            content="I want to improve debug message for context window.",
        ),
        ChatMessage(
            role=MessageRole.ASSISTANT,
            blocks=[ThinkingBlock(content="The user asks for a better log.")],
        ),
        ChatMessage(
            role=MessageRole.ASSISTANT,
            blocks=[
                ToolCallBlock(tool_name="pwd", tool_kwargs={"path": "/"}),
            ],
        ),
        ChatMessage(role=MessageRole.TOOL, content="output: /home/kbush"),
    ]


def agent_input_event(messages):
    """Build the AgentInput event the workflow writes to the stream."""
    from llama_index.core.agent.workflow import AgentInput

    return AgentInput(input=messages, current_agent_name="torvalds")


# ---------------------------------------------------------------------------
# to_string
# ---------------------------------------------------------------------------


class TestToString:
    """What a single message reads as."""

    def test_a_text_message_reads_as_its_text(self):
        message = ChatMessage(role=MessageRole.USER, content="hello there")
        assert to_string(message) == "user: hello there"

    def test_the_role_comes_first(self):
        message = ChatMessage(role=MessageRole.SYSTEM, content="You are Torvalds.")
        assert to_string(message).startswith("system: ")

    def test_a_multi_line_text_stays_multi_line(self):
        message = ChatMessage(role=MessageRole.USER, content="first\nsecond")
        assert to_string(message) == "user: first\nsecond"

    def test_a_thinking_block_is_marked_as_thinking(self):
        message = ChatMessage(
            role=MessageRole.ASSISTANT,
            blocks=[ThinkingBlock(content="let me think about this")],
        )
        assert to_string(message) == "assistant: thinking: let me think about this"

    def test_a_thinking_block_without_content_is_still_marked(self):
        message = ChatMessage(
            role=MessageRole.ASSISTANT,
            blocks=[ThinkingBlock(content=None)],
        )
        assert to_string(message) == "assistant: thinking"

    def test_a_tool_call_block_names_the_tool_and_its_arguments(self):
        message = ChatMessage(
            role=MessageRole.ASSISTANT,
            blocks=[ToolCallBlock(tool_name="ls", tool_kwargs={"path": "/tmp"})],
        )
        assert to_string(message) == "assistant: tool call: ls(path=/tmp)"

    def test_a_tool_call_without_arguments_reads_without_the_parentheses(self):
        message = ChatMessage(
            role=MessageRole.ASSISTANT,
            blocks=[ToolCallBlock(tool_name="pwd", tool_kwargs={})],
        )
        assert to_string(message) == "assistant: tool call: pwd"

    def test_a_tool_call_with_arguments_as_a_string_is_shown(self):
        message = ChatMessage(
            role=MessageRole.ASSISTANT,
            blocks=[ToolCallBlock(tool_name="pwd", tool_kwargs="path=/")],
        )
        assert to_string(message) == "assistant: tool call: pwd(path=/)"

    def test_a_tool_call_in_additional_kwargs_is_shown(self):
        # The OpenAI shape: what an older chat history carries.
        message = ChatMessage(
            role=MessageRole.ASSISTANT,
            content="working on it",
            additional_kwargs={
                "tool_calls": [{"name": "pwd", "arguments": {"path": "/"}}]
            },
        )
        rendered = to_string(message)
        assert "working on it" in rendered
        assert "tool call: pwd(path=/)" in rendered

    def test_a_nested_tool_call_is_shown(self):
        # The shape the Ollama adapter writes.
        message = ChatMessage(
            role=MessageRole.ASSISTANT,
            content="working on it",
            additional_kwargs={
                "tool_calls": [
                    {"function": {"name": "ls", "arguments": {}}}
                ]
            },
        )
        assert "tool call: ls" in to_string(message)

    def test_a_tool_call_shown_twice_is_shown_once(self):
        message = ChatMessage(
            role=MessageRole.ASSISTANT,
            content="working on it",
            additional_kwargs={
                "tool_calls": [{"name": "pwd", "arguments": {"a": 1}}]
            },
            blocks=[ToolCallBlock(tool_name="pwd", tool_kwargs={"a": 1})],
        )
        assert to_string(message).count("tool call: pwd") == 1

    def test_an_image_block_is_marked_as_one(self):
        message = ChatMessage(
            role=MessageRole.USER,
            blocks=[ImageBlock(image=b"\x89PNG", mimetype="image/png")],
        )
        assert to_string(message) == "user: [image]"

    def test_an_empty_message_is_marked_as_empty(self):
        message = ChatMessage(role=MessageRole.ASSISTANT)
        assert to_string(message) == "assistant: (empty)"

    def test_a_message_with_an_empty_text_is_marked_as_empty(self):
        message = ChatMessage(role=MessageRole.USER, content="")
        assert to_string(message) == "user: (empty)"

    def test_a_message_that_is_not_a_message_does_not_raise(self):
        assert to_string(object()) == "?: (empty)"
        assert to_string(None) == "?: (empty)"

    def test_the_parts_of_a_message_are_separated(self):
        message = ChatMessage(
            role=MessageRole.ASSISTANT,
            blocks=[
                ThinkingBlock(content="thinking about it"),
                ToolCallBlock(tool_name="pwd", tool_kwargs={"path": "/"}),
            ],
        )
        rendered = to_string(message)
        assert rendered == (
            "assistant: thinking: thinking about it | tool call: pwd(path=/)"
        )


# ---------------------------------------------------------------------------
# The empty lines
# ---------------------------------------------------------------------------


class TestEmptyLines:
    """The log carries the text, not the paper it is printed on."""

    def test_the_trailing_newlines_of_a_prompt_are_dropped(self):
        message = ChatMessage(
            role=MessageRole.SYSTEM,
            content="You are Torvalds.\n\n\n\n",
        )
        assert to_string(message) == "system: You are Torvalds."

    def test_a_run_of_empty_lines_is_reduced_to_one(self):
        message = ChatMessage(
            role=MessageRole.USER,
            content="first\n\n\n\n\nsecond",
        )
        assert to_string(message) == "user: first\n\nsecond"

    def test_a_paragraph_break_is_kept(self):
        message = ChatMessage(
            role=MessageRole.USER,
            content="first\n\nsecond",
        )
        assert to_string(message) == "user: first\n\nsecond"

    def test_a_message_of_whitespace_is_empty(self):
        message = ChatMessage(role=MessageRole.USER, content="   \n\n  \n")
        assert to_string(message) == "user: (empty)"

    def test_the_trailing_whitespace_of_a_line_is_dropped(self):
        message = ChatMessage(role=MessageRole.USER, content="first   \nsecond\t")
        assert to_string(message) == "user: first\nsecond"

    def test_a_thinking_block_is_tidied_as_well(self):
        message = ChatMessage(
            role=MessageRole.ASSISTANT,
            blocks=[ThinkingBlock(content="thinking\n\n\n")],
        )
        assert to_string(message) == "assistant: thinking: thinking"

    def test_the_leading_empty_lines_are_dropped(self):
        message = ChatMessage(
            role=MessageRole.USER,
            content="\n\nhello",
        )
        assert to_string(message) == "user: hello"


# ---------------------------------------------------------------------------
# to_strings
# ---------------------------------------------------------------------------


class TestToStrings:
    """A whole prompt."""

    def test_it_returns_one_string_per_message(self, prompt):
        assert len(to_strings(prompt)) == len(prompt)

    def test_the_order_is_the_order_of_the_prompt(self, prompt):
        lines = to_strings(prompt)
        assert lines[0].startswith("system: ")
        assert lines[1].startswith("user: ")
        assert lines[4].startswith("tool: ")

    def test_a_payload_that_is_not_a_prompt_has_no_lines(self):
        assert to_strings(None) == []
        assert to_strings("a string") == []
        assert to_strings([]) == []
        assert to_strings(42) == []


# ---------------------------------------------------------------------------
# The integration
# ---------------------------------------------------------------------------


class TestEventConsumerAgentInput:
    """``EventConsumer._on_agent_input``."""

    @pytest.mark.asyncio
    async def test_the_debug_log_carries_the_readable_prompt(
        self, consumer, prompt, caplog
    ):
        with caplog.at_level(logging.DEBUG, logger="components.event_consumer"):
            await consumer._on_agent_input(agent_input_event(prompt))

        text = "\n".join(record.getMessage() for record in caplog.records)
        assert "prompt: 5 messages" in text
        assert "system: You are Torvalds" in text
        assert "user: I want to improve debug message" in text
        assert "thinking: The user asks for a better log." in text
        assert "tool call: pwd(path=/)" in text
        assert "tool: output: /home/kbush" in text

    @pytest.mark.asyncio
    async def test_the_debug_log_does_not_carry_the_repr(
        self, consumer, prompt, caplog
    ):
        with caplog.at_level(logging.DEBUG, logger="components.event_consumer"):
            await consumer._on_agent_input(agent_input_event(prompt))

        text = "\n".join(record.getMessage() for record in caplog.records)
        assert "ChatMessage(role=" not in text
        assert "MessageRole.SYSTEM" not in text
        assert "additional_kwargs=" not in text
        assert "blocks=[" not in text

    @pytest.mark.asyncio
    async def test_every_message_of_the_prompt_is_logged(self, consumer, caplog):
        messages = [
            ChatMessage(role=MessageRole.USER, content=f"message {index}")
            for index in range(25)
        ]
        with caplog.at_level(logging.DEBUG, logger="components.event_consumer"):
            await consumer._on_agent_input(agent_input_event(messages))

        text = "\n".join(record.getMessage() for record in caplog.records)
        assert "prompt: 25 messages" in text
        for index in range(25):
            assert f"message {index}" in text

    @pytest.mark.asyncio
    async def test_the_state_holds_the_readable_text(
        self, consumer, prompt
    ):
        await consumer._on_agent_input(agent_input_event(prompt))
        held = consumer.state.get("agent_input")
        assert "system: You are Torvalds" in held
        assert "tool call: pwd(path=/)" in held
        assert "ChatMessage(role=" not in held

    @pytest.mark.asyncio
    async def test_the_state_holds_no_repr_for_an_odd_payload(self, consumer):
        event = Mock()
        event.input = "not a prompt"
        await consumer._on_agent_input(event)
        held = consumer.state.get("agent_input")
        assert "not a prompt" in held

    @pytest.mark.asyncio
    async def test_a_payload_that_is_not_a_prompt_is_described_briefly(
        self, consumer, caplog
    ):
        # The framework validates the payload of its own event, so the
        # odd payload is delivered the way the handler reads it: through
        # the "input" attribute.
        event = Mock()
        event.input = "not a prompt"
        with caplog.at_level(logging.DEBUG, logger="components.event_consumer"):
            await consumer._on_agent_input(event)

        text = "\n".join(record.getMessage() for record in caplog.records)
        assert "input='not a prompt'" in text

    @pytest.mark.asyncio
    async def test_the_log_carries_no_empty_line(self, consumer, caplog):
        messages = [
            ChatMessage(
                role=MessageRole.SYSTEM,
                content="You are Torvalds.\n\n\n\n",
            ),
            ChatMessage(
                role=MessageRole.USER,
                content="hello\n\n\n\n\nworld",
            ),
        ]
        with caplog.at_level(logging.DEBUG, logger="components.event_consumer"):
            await consumer._on_agent_input(agent_input_event(messages))

        for record in caplog.records:
            message = record.getMessage()
            assert message.strip(), "an empty record was logged"
            assert "\n\n\n" not in message, "a run of empty lines was logged"

    @pytest.mark.asyncio
    async def test_nothing_is_logged_when_debug_is_off(
        self, consumer, prompt, caplog
    ):
        with caplog.at_level(logging.INFO, logger="components.event_consumer"):
            await consumer._on_agent_input(agent_input_event(prompt))

        assert not [
            record
            for record in caplog.records
            if "prompt:" in record.getMessage()
        ]
