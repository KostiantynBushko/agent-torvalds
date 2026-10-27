"""
The verification harness for the answer rendering.

It runs the **real** handlers of ``EventConsumer`` with the **real**
``AgentOutput`` the framework emits, captures the log records they
produce, and checks six invariants:

    O1  the answer is in the log - and the record does not say
        "output=None"
    O2  the tool calls of the answer are in the log, each of them once
    O3  the structured response is in the log
    O4  the retry messages are in the log
    O5  no object syntax leaks into the log - no "ChatMessage(",
        no "MessageRole.", no "AgentOutput("
    O6  a payload that cannot be read does not break the run

Run it:

    self-development/.venv/bin/python \\
        self-development/investigate/output-rendering/verify_output_rendering.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

# The module root may be pointed elsewhere, so the drift harness can run
# the checks against a broken copy of the code.
MODULE_ROOT = Path(
    os.environ.get("TORVALDS_MODULE_ROOT", str(Path(__file__).resolve().parents[2]))
)
sys.path.insert(0, str(MODULE_ROOT))

from rich.console import Console  # noqa: E402

from components.event_consumer import EventConsumer  # noqa: E402
from components.spinner_controller import SpinnerController  # noqa: E402
from components.state_handler import StateHandler  # noqa: E402

from llama_index.core.agent.workflow import AgentOutput  # noqa: E402
from llama_index.core.base.llms.types import ChatMessage, MessageRole  # noqa: E402
from llama_index.core.tools import ToolSelection  # noqa: E402


# ---------------------------------------------------------------------------
# The harness
# ---------------------------------------------------------------------------

class Harness:
    """Collects the checks and prints the verdict."""

    def __init__(self) -> None:
        self.results: list[tuple[str, bool, str]] = []

    def check(self, invariant: str, ok: bool, detail: str = "") -> None:
        self.results.append((invariant, ok, detail))
        mark = "OK  " if ok else "FAIL"
        print(f"[{mark}] {invariant}  {detail}")

    def report(self) -> int:
        failed = [r for r in self.results if not r[1]]
        names = list(dict.fromkeys(r[0] for r in failed))
        print()
        print(f"{len(self.results) - len(failed)}/{len(self.results)} checks hold")
        if failed:
            print("FAILED: " + ", ".join(names))
            return 1
        return 0


class Capture(logging.Handler):
    """Collect the log records the consumer emits."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def text(self) -> str:
        return "\n".join(record.getMessage() for record in self.records)


class _StopEvent:
    """The stop event the framework emits: its result is the answer event."""

    def __init__(self, result) -> None:
        self.result = result


def consume(output: AgentOutput) -> tuple[str, dict]:
    """Run the two handlers over *output* and return the log and the state."""
    logger = logging.getLogger("components.event_consumer")
    logger.setLevel(logging.DEBUG)

    console = Console(quiet=True)
    consumer = EventConsumer(
        spinner_controller=SpinnerController(console),
        state_handler=StateHandler(),
        console=console,
    )

    capture = Capture()
    logger.addHandler(capture)
    try:
        asyncio.run(consumer._on_agent_output(output))
        asyncio.run(consumer._on_stop_event(_StopEvent(output)))
    finally:
        logger.removeHandler(capture)

    return capture.text(), consumer.state.get_state_snapshot()


def build_output() -> AgentOutput:
    """The answer alone."""
    return AgentOutput(
        response=ChatMessage(
            role=MessageRole.ASSISTANT,
            content="The disk is 78% full: 12 GB of 16 GB are in use.",
        ),
        tool_calls=[],
        current_agent_name="torvalds",
    )


def build_output_with_tools() -> AgentOutput:
    """The answer with a tool call the agent asked for."""
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


def build_output_with_everything() -> AgentOutput:
    """The answer with a tool call, a structured response and a retry."""
    return AgentOutput(
        response=ChatMessage(
            role=MessageRole.ASSISTANT,
            content="The disk is 78% full.",
        ),
        tool_calls=[
            ToolSelection(
                tool_id="call-1",
                tool_name="execute_shell_command",
                tool_kwargs={"command": "df -h /"},
            )
        ],
        structured_response={"answer": "78%"},
        retry_messages=[
            ChatMessage(role=MessageRole.ASSISTANT, content="I was not sure.")
        ],
        current_agent_name="torvalds",
    )


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------

def check_o1_the_answer_is_logged(h: Harness) -> None:
    """O1 — the answer is in the log, and the record is not "output=None"."""
    text, _ = consume(build_output())

    has_answer = "The disk is 78% full: 12 GB of 16 GB are in use." in text
    h.check("O1", has_answer, "the text of the answer is in the log")

    not_none = "output=None" not in text
    h.check("O1", not_none, "the record does not say output=None")


def check_o2_the_tool_calls_are_logged(h: Harness) -> None:
    """O2 — the tool calls are in the log, each of them once."""
    text, _ = consume(build_output_with_tools())

    call = "tool call: execute_shell_command(command=df -h /)"
    count = text.count(call)
    h.check("O2", count > 0, f"the tool call is in the log ({count} time(s))")

    # The answer and the stop event both show it - that is two records,
    # not a duplication inside one record.
    once = count == 2
    h.check("O2", once, "the call is shown once per record, not twice")


def check_o3_the_structured_response_is_logged(h: Harness) -> None:
    """O3 — the structured response is in the log."""
    text, _ = consume(build_output_with_everything())
    h.check("O3", "structured:" in text, "the structured response is in the log")


def check_o4_the_retry_messages_are_logged(h: Harness) -> None:
    """O4 — the retry messages are in the log."""
    text, _ = consume(build_output_with_everything())
    h.check("O4", "retry 1:" in text, "the retry message is in the log")


def check_o5_no_object_syntax_leaks(h: Harness) -> None:
    """O5 — no object syntax reaches the log."""
    text, _ = consume(build_output_with_everything())

    leaks = [
        marker
        for marker in ("ChatMessage(", "MessageRole.", "TextBlock(", "AgentOutput(", "ToolSelection(")
        if marker in text
    ]
    h.check("O5", not leaks, f"the leaks: {leaks or 'none'}")


def check_o6_a_broken_payload_does_not_break_the_run(h: Harness) -> None:
    """O6 — a payload that cannot be read does not break the run."""
    class Broken:
        """An answer that explodes when it is looked at."""

        @property
        def response(self):
            raise RuntimeError("the payload is broken")

    logger = logging.getLogger("components.event_consumer")
    logger.setLevel(logging.DEBUG)
    console = Console(quiet=True)
    consumer = EventConsumer(
        spinner_controller=SpinnerController(console),
        state_handler=StateHandler(),
        console=console,
    )

    capture = Capture()
    logger.addHandler(capture)
    raised = False
    try:
        asyncio.run(consumer._on_agent_output(Broken()))
    except Exception:  # noqa: BLE001 — the point of the check
        raised = True
    finally:
        logger.removeHandler(capture)

    h.check("O6", not raised, "the handler survives a payload that raises")


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

def main() -> int:
    print("The answer-rendering invariants")
    print("=" * 70)
    h = Harness()

    check_o1_the_answer_is_logged(h)
    check_o2_the_tool_calls_are_logged(h)
    check_o3_the_structured_response_is_logged(h)
    check_o4_the_retry_messages_are_logged(h)
    check_o5_no_object_syntax_leaks(h)
    check_o6_a_broken_payload_does_not_break_the_run(h)

    return h.report()


if __name__ == "__main__":
    sys.exit(main())
