#!/usr/bin/env python3
"""
Diagnostic #4 — the question identity, the re-ask guard and the answer
book-keeping.

Three further questions the two operator reports point at:

1. **The log timeline.**  The operator's log shows

       19:26:22,428 HITL question detected (hitl-d267a4eb, type=yesno, ...)
       19:26:22,429 HITL answer received for hitl-d267a4eb: 'no'

   one millisecond apart.  The ``workflows`` runtime *replays* a suspended
   step from the beginning when the awaited event arrives, so the question
   is detected a second time on the replay and the already-resolved waiter
   hands the answer back immediately.  This script counts the log lines and
   measures the gap.

2. **The re-ask guard.**  ``HITLFunctionAgent._was_answered()`` compares
   the question *text* for exact equality.  A rephrased question is a
   different string, so the agent asks it again — the operator's "the same
   question twice" observation.

3. **The empty answer.**  ``EventConsumer._collect_answer()`` hard-codes
   ``was_timeout=False`` for a yes/no question, so pressing Enter (the
   default) is indistinguishable from an explicit "no".

Usage::

    .venv/bin/python investigate/hitl-questions-issue/diag_reask.py
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
import sys
from pathlib import Path
from typing import Any, List, Sequence

_HERE = Path(__file__).resolve().parent
_SELF_DEV = _HERE.parents[1]
if str(_SELF_DEV) not in sys.path:
    sys.path.insert(0, str(_SELF_DEV))

from llama_index.core.base.llms.types import ChatMessage, ChatResponse  # noqa: E402
from llama_index.core.llms.callbacks import llm_chat_callback  # noqa: E402
from llama_index.core.llms.mock import MockFunctionCallingLLM  # noqa: E402
from llama_index.core.tools import FunctionTool  # noqa: E402
from pydantic import Field  # noqa: E402
from rich.console import Console  # noqa: E402

from components.event_consumer import EventConsumer  # noqa: E402
from components.hitl_agent import HITLFunctionAgent  # noqa: E402
from components.hitl_events import AgentQuestionEvent  # noqa: E402
from components.spinner_controller import SpinnerController  # noqa: E402
from components.state_handler import StateHandler  # noqa: E402

sys.path.insert(0, str(_HERE / "fixtures"))
from issue_payloads import ISSUE_PAYLOADS  # noqa: E402


def add_two(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


class ScriptedLLM(MockFunctionCallingLLM):
    """Replays a fixed script of assistant messages, one per call."""

    script: List[str] = Field(default_factory=list)
    calls: List[Any] = Field(default_factory=list)

    @llm_chat_callback()
    async def astream_chat(self, messages: Sequence[ChatMessage], **kwargs: Any):
        self.calls.append([(m.role, str(m.content)) for m in messages])
        index = min(len(self.calls) - 1, len(self.script) - 1)
        text = self.script[index]

        async def gen():
            yield ChatResponse(
                message=ChatMessage(role="assistant", content=text),
                delta=text,
                raw={"message": {"role": "assistant", "content": text}},
            )

        return gen()


class RecordingInput:
    def __init__(self, answers: List[str]) -> None:
        self.answers = list(answers)
        self.prompts: List[str] = []

    async def prompt(self, message: str = "", default: str = "", timeout: int = -1) -> str:
        self.prompts.append(message)
        return self._next()

    async def prompt_with_status(self, message: str = "", default: str = "", timeout: int = -1):
        self.prompts.append(message)
        answer = self._next()
        return (answer or default), not answer.strip()

    async def confirm(self, message: str = "", default_yes: bool = True, timeout: int = -1) -> bool:
        self.prompts.append(message)
        answer = self._next()
        if not answer:
            return default_yes
        return answer.strip().lower() in ("y", "yes")

    async def menu(self, message: str = "", options=None, timeout: int = -1) -> str:
        self.prompts.append(message)
        return self._next() or (options or [""])[0]

    async def password(self, message: str = "", timeout: int = -1) -> str:
        self.prompts.append(message)
        return self._next()

    def _next(self) -> str:
        if not self.answers:
            return ""
        return self.answers.pop(0)


class _LogCapture(logging.Handler):
    """Collects the log records of the ``components.hitl_agent`` logger."""

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.records: List[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def messages(self) -> List[str]:
        return [r.getMessage() for r in self.records]


def run(script: List[str], answers: List[str]) -> dict:
    """Run one scripted conversation and return what happened."""
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=100, highlight=False)

    consumer = EventConsumer(
        spinner_controller=SpinnerController(console=console),
        state_handler=StateHandler(),
        console=console,
        hitl_timeout=-1,
        hitl_default_answer="no",
    )
    recorder = RecordingInput(answers)
    consumer.console_input = recorder

    llm = ScriptedLLM(script=script)
    agent = HITLFunctionAgent(
        tools=[FunctionTool.from_defaults(fn=add_two)],
        llm=llm,
        hitl_enabled=True,
        hitl_default_timeout=-1,
        hitl_default_answer="no",
    )

    capture = _LogCapture()
    logger = logging.getLogger("components.hitl_agent")
    logger.setLevel(logging.INFO)
    logger.addHandler(capture)

    async def _drive() -> None:
        handler = agent.run("go")
        await consumer.consume_events(handler, "go")

    try:
        asyncio.run(_drive())
    finally:
        logger.removeHandler(capture)

    return {
        "prompts": recorder.prompts,
        "logs": capture.messages(),
        "llm_calls": llm.calls,
        "console": buffer.getvalue(),
    }


def main() -> int:
    print("=" * 78)
    print("DIAGNOSTIC #4 — question identity, re-ask guard, answer book-keeping")
    print("=" * 78)
    failures = 0

    # ------------------------------------------------------------------
    # 1. The log timeline.
    # ------------------------------------------------------------------
    print()
    print("-" * 78)
    print("1. Log timeline for a single question")
    print("-" * 78)
    out = run(
        script=[ISSUE_PAYLOADS["duplicate-question"], "All done."],
        answers=["no"],
    )
    detected = [m for m in out["logs"] if "HITL question detected" in m]
    received = [m for m in out["logs"] if "HITL answer received" in m]
    print(f"'HITL question detected' log lines : {len(detected)}")
    for line in detected:
        print(f"    {line}")
    print(f"'HITL answer received' log lines  : {len(received)}")
    for line in received:
        print(f"    {line}")
    if len(detected) > 1:
        print("  => VERDICT: the question is DETECTED more than once — the workflow")
        print("     runtime replays the suspended step, and the step re-detects the")
        print("     question before it consumes the already-resolved waiter.")
        failures += 1
    else:
        print("  => the question is detected once.")

    # ------------------------------------------------------------------
    # 2. The re-ask guard.
    # ------------------------------------------------------------------
    print()
    print("-" * 78)
    print("2. Re-ask guard — the same question, rephrased")
    print("-" * 78)
    q1 = "Shall I create the branch feature/sqitch-database-migrations?"
    q2 = "Should I create the branch feature/sqitch-database-migrations?"
    out = run(script=[q1, q2, "All done."], answers=["no", "no"])
    asked = len(out["prompts"])
    print(f"question #1 : {q1}")
    print(f"question #2 : {q2}   <- the same question, rephrased")
    print(f"prompts shown to the operator : {asked}")
    if asked > 1:
        print("  => VERDICT: the rephrased question is asked AGAIN — the guard")
        print("     compares the question text for exact equality.")
        failures += 1
    else:
        print("  => the rephrased question was not asked again.")

    # ------------------------------------------------------------------
    # 2b. A question that ends with a code span is not detected at all.
    # ------------------------------------------------------------------
    print()
    print("-" * 78)
    print("2b. Detection — a question that ends with a code span")
    print("-" * 78)
    from components.hitl_agent import is_question  # noqa: PLC0415

    probes = [
        "Shall I create the branch feature/sqitch?",
        "Shall I create the branch `feature/sqitch`?",
        "Shall I create the branch \"feature/sqitch\"?",
        "Shall I proceed?",
    ]
    for probe in probes:
        detected = is_question(probe)
        print(f"    detected={detected!s:<5} {probe}")
        if not detected:
            failures += 1
    print("  => a question whose last character before '?' is not a word character")
    print("     (a closing backtick or quote) is not detected at all: the pattern")
    print("     r'\\w+\\s*\\?$' cannot match it.")

    # ------------------------------------------------------------------
    # 3. The empty answer.
    # ------------------------------------------------------------------
    print()
    print("-" * 78)
    print("3. An empty answer (the user just presses Enter)")
    print("-" * 78)
    out = run(
        script=[ISSUE_PAYLOADS["duplicate-question"], "All done."],
        answers=[""],  # the operator presses Enter
    )
    received = [m for m in out["logs"] if "HITL answer received" in m]
    for line in received:
        print(f"    {line}")
    if received and "timeout=False" in received[0] and "'no'" in received[0]:
        print("  => VERDICT: the empty answer is recorded as an explicit 'no', not")
        print("     as a timeout — the operator cannot tell the two apart.")
        failures += 1
    else:
        print("  => the empty answer is reported as a timeout.")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print()
    print("=" * 78)
    if failures:
        print(f"RESULT: {failures} further defect(s) reproduced.")
        print("        The defects are CONFIRMED.")
    else:
        print("RESULT: no further defect reproduced.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
