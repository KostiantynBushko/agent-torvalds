#!/usr/bin/env python3
"""
Verification harness — the invariants a readable chat message must satisfy.

Run it against the current tree to see which invariants are violated:

    .venv/bin/python investigate/chat-message-debug/verify_chat_message.py

Exit code 0 = every invariant holds.  Exit code 1 = at least one is broken.

The harness is written against the *public* behaviour — the log records
the event consumer writes, and the state it keeps — rather than against
private helpers, so it stays valid when the implementation is refactored.

Invariants
----------
I1  The debug log carries a **readable** prompt: the role and the
    content of every message — and none of the object syntax the raw
    dump used to show.
I2  **Every** message of the prompt is in the log.  A report that
    shows the first few and drops the rest is the dump it replaced.
I3  A tool call is visible in every shape a message can carry one: as a
    block, as the OpenAI-shaped ``additional_kwargs``, and as the nested
    shape the Ollama adapter writes.
I4  The state holds the readable text.  It never holds the repr of the
    whole conversation.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Callable, List, Sequence, Tuple

_HERE = Path(__file__).resolve().parent
_SELF_DEV = _HERE.parents[1]
if str(_SELF_DEV) not in sys.path:
    sys.path.insert(0, str(_SELF_DEV))

from llama_index.core.agent.workflow import AgentInput  # noqa: E402
from llama_index.core.base.llms.types import (  # noqa: E402
    ChatMessage,
    MessageRole,
    ToolCallBlock,
)
from rich.console import Console  # noqa: E402

from components.chat_message import to_string  # noqa: E402
from components.event_consumer import EventConsumer  # noqa: E402
from components.spinner_controller import SpinnerController  # noqa: E402
from components.state_handler import StateHandler  # noqa: E402

LOGGER_NAME = "components.event_consumer"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_consumer(**kwargs: Any) -> EventConsumer:
    """Return an EventConsumer wired to a real console and state."""
    console = Console(force_terminal=True, width=100)
    return EventConsumer(
        spinner_controller=SpinnerController(console=console),
        state_handler=StateHandler(),
        console=console,
        **kwargs,
    )


def sample_prompt() -> List[ChatMessage]:
    """Return a small but realistic prompt."""
    return [
        ChatMessage(
            role=MessageRole.SYSTEM,
            content="You are Torvalds, a technical AI assistant.",
        ),
        ChatMessage(
            role=MessageRole.USER,
            content="I want to improve the debug message for the context window.",
        ),
        ChatMessage(
            role=MessageRole.ASSISTANT,
            content="thinking: The user wants a readable prompt.",
        ),
        ChatMessage(
            role=MessageRole.ASSISTANT,
            blocks=[
                ToolCallBlock(tool_name="pwd", tool_kwargs={"path": "/"}),
            ],
        ),
        ChatMessage(role=MessageRole.TOOL, content="output: /home/kbush"),
    ]


async def consume(consumer: EventConsumer, messages: Any) -> str:
    """Feed *messages* to the consumer and return the log text."""
    records: List[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture()
    logger = logging.getLogger(LOGGER_NAME)
    previous_level = logger.level
    previous_propagate = logger.propagate
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    try:
        await consumer._on_agent_input(
            AgentInput(input=messages, current_agent_name="torvalds")
        )
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate

    return "\n".join(record.getMessage() for record in records)


# ---------------------------------------------------------------------------
# The invariants
# ---------------------------------------------------------------------------


async def i1_the_log_is_readable() -> Tuple[bool, str]:
    """The debug log carries a readable prompt, not the object syntax."""
    consumer = make_consumer()
    text = await consume(consumer, sample_prompt())

    problems = []
    if "prompt:" not in text:
        problems.append("no summary line")
    for role in ("system", "user", "assistant", "tool"):
        if role not in text:
            problems.append(f"the {role} messages are not visible")
    for forbidden in (
        "ChatMessage(role=",
        "MessageRole.SYSTEM",
        "additional_kwargs=",
        "blocks=[",
    ):
        if forbidden in text:
            problems.append(f"the raw dump is still there: {forbidden}")

    return (not problems, "; ".join(problems) or "readable")


async def i2_every_message_is_logged() -> Tuple[bool, str]:
    """Every message of the prompt is in the log."""
    messages = sample_prompt() + [
        ChatMessage(role=MessageRole.ASSISTANT, content=f"step {index}")
        for index in range(30)
    ]
    consumer = make_consumer()
    text = await consume(consumer, messages)

    problems = []
    if "prompt: 35 messages" not in text:
        problems.append("the summary does not count the whole prompt")
    for index in range(30):
        if f"step {index}" not in text:
            problems.append(f"message {index} is missing")
            break

    return (not problems, "; ".join(problems) or "every message is logged")


async def i3_tool_calls_are_visible() -> Tuple[bool, str]:
    """A tool call is visible in every shape a message can carry one."""
    shapes = {
        "block": ChatMessage(
            role=MessageRole.ASSISTANT,
            blocks=[ToolCallBlock(tool_name="pwd", tool_kwargs={})],
        ),
        "openai": ChatMessage(
            role=MessageRole.ASSISTANT,
            content="working",
            additional_kwargs={"tool_calls": [{"name": "pwd", "arguments": {}}]},
        ),
        "nested": ChatMessage(
            role=MessageRole.ASSISTANT,
            content="working",
            additional_kwargs={
                "tool_calls": [{"function": {"name": "pwd", "arguments": {}}}]
            },
        ),
    }

    problems = []
    for name, message in shapes.items():
        if "pwd" not in to_string(message):
            problems.append(f"the {name} shape is not visible")

    return (not problems, "; ".join(problems) or "every shape is visible")


async def i4_the_state_is_readable() -> Tuple[bool, str]:
    """The state holds the readable text, never the repr."""
    consumer = make_consumer()
    await consume(consumer, sample_prompt())
    held = consumer.state.get("agent_input")

    problems = []
    if not isinstance(held, str):
        problems.append("the state holds no text")
    elif "ChatMessage(role=" in held:
        problems.append("the state holds the repr")
    elif "system: You are Torvalds" not in held:
        problems.append("the state holds no readable prompt")

    return (not problems, "; ".join(problems) or "the state is readable")


INVARIANTS: Sequence[Tuple[str, Callable[[], Any]]] = (
    ("I1  the log is readable", i1_the_log_is_readable),
    ("I2  every message is logged", i2_every_message_is_logged),
    ("I3  tool calls are visible", i3_tool_calls_are_visible),
    ("I4  the state is readable", i4_the_state_is_readable),
)


async def main() -> int:
    print("Chat message — the invariants a readable prompt must satisfy")
    print("=" * 70)

    failures = 0
    for name, check in INVARIANTS:
        ok, detail = await check()
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}: {detail}")
        if not ok:
            failures += 1

    print("=" * 70)
    if failures:
        print(f"FAIL — {failures} of {len(INVARIANTS)} invariants are broken.")
        return 1

    print(f"PASS — all {len(INVARIANTS)} invariants hold.")
    return 0


if __name__ == "__main__":
    import asyncio

    sys.exit(asyncio.run(main()))
