"""
The probe: what does the event consumer actually log for the agent's
answer?

It calls the **real** handlers of ``EventConsumer`` with a **real**
``AgentOutput`` built by the installed LlamaIndex, and captures the log
records they produce.

Run it:

    self-development/.venv/bin/python \\
        self-development/investigate/output-rendering/probe_output_rendering.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rich.console import Console  # noqa: E402

from components.event_consumer import EventConsumer  # noqa: E402
from components.spinner_controller import SpinnerController  # noqa: E402
from components.state_handler import StateHandler  # noqa: E402

from llama_index.core.agent.workflow import AgentOutput  # noqa: E402
from llama_index.core.base.llms.types import ChatMessage, MessageRole  # noqa: E402


class Capture(logging.Handler):
    """Collect the log records the consumer emits."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def messages(self) -> list[str]:
        return [record.getMessage() for record in self.records]


def build_output() -> AgentOutput:
    """Build the output event the framework really emits."""
    return AgentOutput(
        response=ChatMessage(
            role=MessageRole.ASSISTANT,
            content="The disk is 78% full: 12 GB of 16 GB are in use.",
        ),
        tool_calls=[],
        current_agent_name="torvalds",
    )


def build_output_with_tools() -> AgentOutput:
    """Build an output event that carries tool calls."""
    from llama_index.core.tools import ToolSelection

    return AgentOutput(
        response=ChatMessage(
            role=MessageRole.ASSISTANT,
            content="Let me look at the disk.",
        ),
        tool_calls=[
            ToolSelection(
                tool_id="call-1",
                tool_name="execute_shell_command",
                tool_kwargs={"command": "df -h /"},
            )
        ],
        current_agent_name="torvalds",
    )


def run() -> None:
    logger = logging.getLogger("components.event_consumer")
    logger.setLevel(logging.DEBUG)

    console = Console(quiet=True)
    consumer = EventConsumer(
        spinner_controller=SpinnerController(console),
        state_handler=StateHandler(),
        console=console,
    )

    for title, output in (
        ("the answer alone", build_output()),
        ("the answer with a tool call", build_output_with_tools()),
    ):
        capture = Capture()
        logger.addHandler(capture)

        asyncio.run(consumer._on_agent_output(AgentOutput(**output.model_dump())))
        asyncio.run(consumer._on_stop_event(_StopEvent(output)))

        logger.removeHandler(capture)

        print(f"=== {title} ===")
        for message in capture.messages():
            print(f"  {message}")
        print()

    print("=== what the raw repr looks like (the stop event today) ===")
    output = build_output_with_tools()
    print(f"  {output!r}")
    print()


class _StopEvent:
    """The stop event the framework emits: its result is the AgentOutput."""

    def __init__(self, result) -> None:
        self.result = result


if __name__ == "__main__":
    run()
