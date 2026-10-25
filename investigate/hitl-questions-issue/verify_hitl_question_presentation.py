#!/usr/bin/env python3
"""
Verification harness — the invariants a correct HITL question presentation
must satisfy.

Run it against the current tree to see which invariants are violated:

    .venv/bin/python investigate/hitl-questions-issue/verify_hitl_question_presentation.py

Exit code 0 = every invariant holds.  Exit code 1 = at least one is broken.

The harness is deliberately written against the *public* behaviour (the
event stream, the console output, the log records) rather than against
private helpers, so it stays valid when the implementation is refactored.

Invariants
----------
I1  A question is rendered for the operator **exactly once**.
I2  The event carries the *question*, not the whole answer; the rest of the
    answer travels in ``context``.
I3  The input type is derived from the question alone, with word-boundary
    matching — a report that merely mentions "secret" must not turn into a
    password prompt.
I4  A password question is still shown to the operator.
I5  A rephrased question is not asked twice.
I6  An empty answer (Enter) is reported as a timeout, not as an explicit "no".
I7  A question that ends with a code span is detected.
I8  A question is *detected* once, not once per workflow replay.
I9  A decorated question — quoted, emphasised or labelled — is asked as the
    open question it is, not as a yes/no question.
"""

from __future__ import annotations

import asyncio
import io
import logging
import sys
from pathlib import Path
from typing import Any, Callable, List, Sequence, Tuple

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


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

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
    """Console input double: records the prompts and replays the answers."""

    def __init__(self, answers: Sequence[str] = ()) -> None:
        self.answers = list(answers)
        self.prompts: List[str] = []

    def _next(self) -> str:
        if not self.answers:
            return ""
        return self.answers.pop(0)

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

    async def menu_with_status(
        self, message: str = "", options=None, timeout: int = -1
    ) -> Tuple[str, bool]:
        """Mirrors ``ConsoleInputModule.menu_with_status``."""
        self.prompts.append(message)
        answer = self._next()
        choices = list(options or [])
        if not choices:
            return "", True
        if not answer.strip():
            return choices[0], True
        try:
            index = int(answer.strip()) - 1
            if 0 <= index < len(choices):
                return choices[index], False
        except ValueError:
            pass
        return choices[0], False

    async def password(self, message: str = "", timeout: int = -1) -> str:
        self.prompts.append(message)
        return self._next()


class _LogCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.messages: List[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def _normalise(text: str) -> str:
    return " ".join(text.split())


def run(script: Sequence[str], answers: Sequence[str] = ("no",)) -> dict:
    """Run one scripted conversation through the real HITL stack."""
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

    llm = ScriptedLLM(script=list(script))
    agent = HITLFunctionAgent(
        tools=[FunctionTool.from_defaults(fn=add_two)],
        llm=llm,
        hitl_enabled=True,
        hitl_default_timeout=-1,
        hitl_default_answer="no",
    )

    question_events: List[AgentQuestionEvent] = []
    capture = _LogCapture()
    logger = logging.getLogger("components.hitl_agent")
    logger.setLevel(logging.INFO)
    logger.addHandler(capture)

    async def _drive() -> None:
        handler = agent.run("go")
        original_stream = handler.stream_events

        async def tapped():
            async for event in original_stream():
                if isinstance(event, AgentQuestionEvent):
                    question_events.append(event)
                yield event

        handler.stream_events = tapped
        await consumer.consume_events(handler, "go")

    try:
        asyncio.run(_drive())
    finally:
        logger.removeHandler(capture)

    console_out = buffer.getvalue()
    return {
        "events": question_events,
        "prompts": recorder.prompts,
        "console": console_out,
        "logs": capture.messages,
        "llm_calls": llm.calls,
    }


def renderings(out: dict, text: str) -> int:
    """Count how often *text* reaches the operator."""
    needle = _normalise(text)
    if not needle:
        return 0
    total = _normalise(out["console"]).count(needle)
    for prompt in out["prompts"]:
        total += _normalise(prompt).count(needle)
    return total


# ---------------------------------------------------------------------------
# The invariants
# ---------------------------------------------------------------------------

def i1_rendered_once() -> Tuple[bool, str]:
    """I1 — a question is rendered exactly once.

    The operator saw the whole message twice.  The question and the report
    around it are now rendered separately — the report as the context, the
    question as the question — and the choices of a menu are rendered as
    the menu, so the *payload* is no longer one contiguous block.  What
    matters is that the question reaches the operator exactly once, that
    the report above it is still visible, and that the input module never
    repeats either of them.
    """
    out = run([ISSUE_PAYLOADS["duplicate-question"], "All done."], answers=["no"])
    question = "Also, would you like me to:"
    times = renderings(out, question)
    if times != 1:
        return False, f"the question was rendered {times} time(s), expected 1"
    if not renderings(out, "Current status:"):
        return False, "the report around the question was not shown"
    for prompt in out["prompts"]:
        if question.lower() in prompt.lower():
            return False, "the input module repeated the question"
    return True, "the question is rendered once, the report above it"


def i2_question_not_answer() -> Tuple[bool, str]:
    """I2 — the event carries the question; the rest goes into ``context``."""
    payload = ISSUE_PAYLOADS["wrong-question"]
    out = run([payload, "All done."], answers=["no"])
    if not out["events"]:
        return False, "no AgentQuestionEvent was produced"
    event = out["events"][0]
    if len(event.question) >= len(payload):
        return False, (
            f"the event question is {len(event.question)} characters — the whole "
            f"answer ({len(payload)} characters) was used as the question"
        )
    if not event.context:
        return False, "the rest of the answer was dropped (context is empty)"
    return True, "the question is separated from the surrounding answer"


def i3_input_type_from_question() -> Tuple[bool, str]:
    """I3 — the input type follows the question, not the whole answer."""
    from components.hitl_agent import detect_input_type

    payload = ISSUE_PAYLOADS["wrong-question"]
    detected = detect_input_type(payload)
    if detected == "password":
        return False, (
            "an answer that merely mentions 'secret' is classified as a "
            "password request"
        )
    return True, f"the answer is classified as {detected!r}"


def i4_password_question_is_shown() -> Tuple[bool, str]:
    """I4 — a password question is still shown to the operator."""
    out = run(["What is the sudo password?", "All done."], answers=["hunter2"])
    shown = any("sudo password" in p for p in out["prompts"])
    console = out["console"]
    if not shown and "sudo password" not in console:
        return False, "the password question was never shown to the operator"
    return True, "the password question is shown"


def i5_no_reask_after_rephrasing() -> Tuple[bool, str]:
    """I5 — a rephrased question is not asked twice."""
    q1 = "Shall I create the branch feature/sqitch-database-migrations?"
    q2 = "Should I create the branch feature/sqitch-database-migrations?"
    out = run([q1, q2, "All done."], answers=["no", "no"])
    asked = len(out["prompts"])
    return asked <= 1, f"the operator was prompted {asked} time(s), expected 1"


def i6_empty_answer_is_a_timeout() -> Tuple[bool, str]:
    """I6 — an empty answer is reported as a timeout."""
    out = run([ISSUE_PAYLOADS["duplicate-question"], "All done."], answers=[""])
    received = [m for m in out["logs"] if "HITL answer received" in m]
    if not received:
        return False, "no answer was recorded"
    if "timeout=True" not in received[0]:
        return False, f"the empty answer was recorded as {received[0]!r}"
    return True, "the empty answer is recorded as a timeout"


def i7_code_span_question_detected() -> Tuple[bool, str]:
    """I7 — a question ending with a code span is detected."""
    from components.hitl_agent import is_question

    probe = "Shall I create the branch `feature/sqitch`?"
    detected = is_question(probe)
    return detected, f"detected={detected}"


def i8_detected_once() -> Tuple[bool, str]:
    """I8 — a question is detected once, not once per workflow replay."""
    out = run([ISSUE_PAYLOADS["duplicate-question"], "All done."], answers=["no"])
    detected = [m for m in out["logs"] if "HITL question detected" in m]
    return len(detected) <= 1, (
        f"the question was detected {len(detected)} time(s), expected 1"
    )


def i9_decorated_question_is_not_yes_no() -> Tuple[bool, str]:
    """I9 — a decorated question is not prompted as a yes/no question.

    The operator reported that a question with three choices was prompted
    with ``[y/N]``: the agent had written the question quoted and labelled
    (``question: 'Which one should I use?'``), and the wrapping hid the
    question word from the rules.
    """
    message = (
        "I found three options.\n"
        "\n"
        "question: 'Which one should I use?'"
    )
    out = run([message, "All done."], answers=["the first one"])
    if not out["events"]:
        return False, "no AgentQuestionEvent was produced"
    event = out["events"][0]
    if event.input_type == "yesno":
        return False, (
            "the question is typed 'yesno' — the operator is prompted with "
            "[y/N] for a question that asks for a choice"
        )
    if event.question != "Which one should I use?":
        return False, (
            f"the operator reads {event.question!r} — the wrapping is still "
            "part of the question"
        )
    if any("[y/N]" in prompt for prompt in out["prompts"]):
        return False, f"the prompt was a yes/no prompt: {out['prompts']!r}"
    return True, "the question is asked as the open question it is"


INVARIANTS: List[Tuple[str, Callable[[], Tuple[bool, str]]]] = [
    ("I1  the question is rendered exactly once", i1_rendered_once),
    ("I2  the event carries the question, not the whole answer", i2_question_not_answer),
    ("I3  the input type follows the question alone", i3_input_type_from_question),
    ("I4  a password question is still shown", i4_password_question_is_shown),
    ("I5  a rephrased question is not asked twice", i5_no_reask_after_rephrasing),
    ("I6  an empty answer is reported as a timeout", i6_empty_answer_is_a_timeout),
    ("I7  a question ending with a code span is detected", i7_code_span_question_detected),
    ("I8  a question is detected once per question", i8_detected_once),
    ("I9  a decorated question is not a yes/no question", i9_decorated_question_is_not_yes_no),
]


def main() -> int:
    print("=" * 78)
    print("VERIFICATION — HITL question presentation invariants")
    print("=" * 78)

    passed = 0
    failed: List[str] = []

    for label, check in INVARIANTS:
        try:
            ok, detail = check()
        except Exception as exc:  # noqa: BLE001 - a raising check is a failing check
            ok, detail = False, f"the check raised {type(exc).__name__}: {exc}"
        if ok:
            passed += 1
            print(f"  PASS  {label}")
            print(f"        {detail}")
        else:
            failed.append(label)
            print(f"  FAIL  {label}")
            print(f"        {detail}")

    total = len(INVARIANTS)
    print()
    print("=" * 78)
    print(f"{passed}/{total} invariants hold, {len(failed)} violated.")
    if failed:
        for label in failed:
            print(f"  - {label}")
        print()
        print("The defects reported by the operator are still present.")
    else:
        print("Every invariant holds — the HITL question presentation is correct.")
    print("=" * 78)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
