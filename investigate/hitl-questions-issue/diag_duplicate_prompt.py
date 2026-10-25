#!/usr/bin/env python3
"""
Diagnostic #2 — the same question is rendered twice.

What the operator reported (``hitl_dublicate_question.md``)
-----------------------------------------------------------
The agent asked a question; the operator saw the *whole message* twice on
the console.

Why
---
``components/event_consumer.py`` renders the question in **two** places:

1. ``_on_agent_question()`` — ``console.print("🤖 Agent asks: {question}")``
2. ``_collect_answer()`` — for ``input_type == "yesno"`` it calls
   ``console_input.confirm(message=event.question, ...)``, and
   ``ConsoleInputModule.confirm()`` builds
   ``f"{message}{suffix}"`` and hands it to ``input()`` — which writes the
   message to stdout *again*, followed by ``[y/N]``.

So for a yes/no question the payload is printed twice; for a ``menu``
question it is printed twice as well (``ConsoleInputModule.menu()`` does
``console.print(f"\\n{message}")``).  For a ``text`` question it is printed
once (the prompt is a fixed "Your response: "), and for a ``password``
question the question is *never* printed at all.

This script renders both operator payloads through the *real*
``EventConsumer`` and counts how many times the payload reaches the
terminal.

Usage::

    .venv/bin/python investigate/hitl-questions-issue/diag_duplicate_prompt.py
"""

from __future__ import annotations

import asyncio
import io
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SELF_DEV = _HERE.parents[1]
if str(_SELF_DEV) not in sys.path:
    sys.path.insert(0, str(_SELF_DEV))

from rich.console import Console  # noqa: E402

from components.event_consumer import EventConsumer  # noqa: E402
from components.hitl_events import AgentQuestionEvent  # noqa: E402
from components.spinner_controller import SpinnerController  # noqa: E402
from components.state_handler import StateHandler  # noqa: E402

sys.path.insert(0, str(_HERE / "fixtures"))
from issue_payloads import ISSUE_PAYLOADS  # noqa: E402


class RecordingInput:
    """Stand-in for the console input module that records every prompt."""

    def __init__(self, answer: str = "no") -> None:
        self.answer = answer
        self.prompts: list[str] = []

    async def prompt(self, message: str = "", default: str = "", timeout: int = -1) -> str:
        self.prompts.append(message)
        return self.answer

    async def prompt_with_status(self, message: str = "", default: str = "", timeout: int = -1):
        self.prompts.append(message)
        return self.answer, False

    async def confirm(self, message: str = "", default_yes: bool = True, timeout: int = -1) -> bool:
        self.prompts.append(message)
        return self.answer.strip().lower() in ("y", "yes")

    async def menu(self, message: str = "", options=None, timeout: int = -1) -> str:
        self.prompts.append(message)
        return (options or [""])[0]

    async def password(self, message: str = "", timeout: int = -1) -> str:
        self.prompts.append(message)
        return self.answer


class _MockWorkflowHandler:
    """Minimal stand-in for the workflow handler."""

    def __init__(self) -> None:
        self.sent = []
        self.ctx = self

    def send_event(self, event) -> None:
        self.sent.append(event)


def render(question: str, input_type: str) -> tuple[str, list[str]]:
    """Render one question through the real consumer.

    Returns ``(terminal_output, prompts)``.
    """
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=100, highlight=False)
    consumer = EventConsumer(
        spinner_controller=SpinnerController(console=console),
        state_handler=StateHandler(),
        console=console,
        hitl_timeout=-1,
        hitl_default_answer="no",
    )
    recorder = RecordingInput("no")
    consumer.console_input = recorder
    consumer._current_handler = _MockWorkflowHandler()

    event = AgentQuestionEvent(
        question=question,
        question_id="diag-1",
        timeout=-1,
        default_answer="no",
        input_type=input_type,
    )

    asyncio.run(consumer._on_agent_question(event))
    return buffer.getvalue(), recorder.prompts


def _normalise(text: str) -> str:
    """Collapse whitespace so a wrapped console line still matches."""
    return " ".join(text.split())


def occurrences(haystack: str, needle: str) -> int:
    """Count how many times *needle* occurs in *haystack*.

    The console wraps long lines, so both sides are whitespace-normalised
    before the count — otherwise a wrapped question would look like it was
    never printed.
    """
    needle_n = _normalise(needle)
    if not needle_n:
        return 0
    return _normalise(haystack).count(needle_n)


def main() -> int:
    print("=" * 78)
    print("DIAGNOSTIC #2 — the HITL question is rendered twice")
    print("=" * 78)

    failures = 0

    for name, text in ISSUE_PAYLOADS.items():
        # The input type the *current* detector produces for this payload.
        from components.hitl_agent import detect_input_type

        input_type = detect_input_type(text)
        output, prompts = render(text, input_type)

        print()
        print(f"--- payload: {name} " + "-" * (58 - len(name)))
        print(f"detected input_type     : {input_type!r}")
        print(f"prompts handed to input : {len(prompts)}")
        for i, p in enumerate(prompts, 1):
            first = p.strip().splitlines()[0] if p.strip() else ""
            print(f"    prompt #{i}: {p!r}")
            print(f"             first line: {first!r}")

        console_hits = occurrences(output, text)
        prompt_hits = sum(occurrences(p, text) for p in prompts)

        print(f"times the payload is printed by console.print : {console_hits}")
        print(f"times the payload is printed by the input prompt: {prompt_hits}")
        print(f"TOTAL times the operator sees the payload       : {console_hits + prompt_hits}")

        if console_hits + prompt_hits > 1:
            print("  => VERDICT: DUPLICATED — the payload reaches the terminal twice.")
            failures += 1
        elif console_hits + prompt_hits == 0:
            print("  => VERDICT: the payload is never shown at all (the question is lost).")
            failures += 1
        else:
            print("  => VERDICT: shown once.")

    # The matrix of every input type.
    print()
    print("-" * 78)
    print("Render matrix (question = 'Shall I continue?')")
    print("-" * 78)
    matrix_question = "Shall I continue?"
    for input_type in ("text", "yesno", "menu", "password"):
        output, prompts = render(matrix_question, input_type)
        times = occurrences(output, matrix_question) + sum(
            occurrences(p, matrix_question) for p in prompts
        )
        print(f"  input_type={input_type:<9} -> the question is shown {times} time(s)")

    print()
    print("=" * 78)
    if failures:
        print(f"RESULT: {failures} rendering defect(s) reproduced.")
        print("        The defect is CONFIRMED.")
    else:
        print("RESULT: no rendering defect reproduced.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
