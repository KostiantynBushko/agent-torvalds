#!/usr/bin/env python3
"""
Diagnostic #3 — the full HITL round-trip, observed end to end.

This runs the *real* ``HITLFunctionAgent`` inside the *real* ``workflows``
runtime, with the real ``EventConsumer`` attached, and records:

* how many ``AgentQuestionEvent`` objects reach the event stream,
* how many times the question is *rendered* for the operator,
* which input type was chosen and which prompt was shown,
* how long the answer took to arrive,
* whether the same question is asked more than once.

The mock LLM replays the two verbatim operator payloads, so the behaviour
measured here is the behaviour the operator saw.

Usage::

    .venv/bin/python investigate/hitl-questions-issue/diag_roundtrip.py
"""

from __future__ import annotations

import asyncio
import io
import sys
import time
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


class ReplayLLM(MockFunctionCallingLLM):
    """Answers with *payload* first, then with a short final message."""

    payload: str = ""
    final: str = "Understood."
    calls: List[Any] = Field(default_factory=list)

    @llm_chat_callback()
    async def astream_chat(self, messages: Sequence[ChatMessage], **kwargs: Any):
        self.calls.append([(m.role, str(m.content)) for m in messages])
        text = self.payload if len(self.calls) == 1 else self.final

        async def gen():
            yield ChatResponse(
                message=ChatMessage(role="assistant", content=text),
                delta=text,
                raw={"message": {"role": "assistant", "content": text}},
            )

        return gen()


class RecordingInput:
    """Console input double that records every prompt and its timing."""

    def __init__(self, answer: str = "no", delay: float = 0.0) -> None:
        self.answer = answer
        self.delay = delay
        self.prompts: List[str] = []
        self.asked_at: List[float] = []

    async def prompt(self, message: str = "", default: str = "", timeout: int = -1) -> str:
        self.prompts.append(message)
        self.asked_at.append(time.monotonic())
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.answer

    async def prompt_with_status(self, message: str = "", default: str = "", timeout: int = -1):
        self.prompts.append(message)
        self.asked_at.append(time.monotonic())
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.answer, False

    async def confirm(self, message: str = "", default_yes: bool = True, timeout: int = -1) -> bool:
        self.prompts.append(message)
        self.asked_at.append(time.monotonic())
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.answer.strip().lower() in ("y", "yes")

    async def menu(self, message: str = "", options=None, timeout: int = -1) -> str:
        self.prompts.append(message)
        self.asked_at.append(time.monotonic())
        return (options or [""])[0]

    async def password(self, message: str = "", timeout: int = -1) -> str:
        self.prompts.append(message)
        self.asked_at.append(time.monotonic())
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.answer


def _normalise(text: str) -> str:
    return " ".join(text.split())


def run_case(name: str, payload: str, answer: str = "no") -> dict:
    """Run one operator payload through the full HITL round-trip."""
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=100, highlight=False)

    consumer = EventConsumer(
        spinner_controller=SpinnerController(console=console),
        state_handler=StateHandler(),
        console=console,
        hitl_timeout=-1,
        hitl_default_answer="no",
    )
    recorder = RecordingInput(answer)
    consumer.console_input = recorder

    llm = ReplayLLM(payload=payload)
    agent = HITLFunctionAgent(
        tools=[FunctionTool.from_defaults(fn=add_two)],
        llm=llm,
        hitl_enabled=True,
        hitl_default_timeout=-1,
        hitl_default_answer="no",
    )

    question_events: List[AgentQuestionEvent] = []

    async def _run() -> Any:
        handler = agent.run("do the work")

        # Tap the stream so every event the consumer sees is also recorded
        # by the diagnostic, then let the consumer drive the run exactly
        # like the real orchestrators do.
        original_stream = handler.stream_events

        async def tapped_stream():
            async for event in original_stream():
                if isinstance(event, AgentQuestionEvent):
                    question_events.append(event)
                yield event

        handler.stream_events = tapped_stream
        return await consumer.consume_events(handler, "do the work")

    started = time.monotonic()
    result = asyncio.run(_run())
    elapsed = time.monotonic() - started

    output = buffer.getvalue()
    return {
        "name": name,
        "payload": payload,
        "question_events": question_events,
        "prompts": recorder.prompts,
        "console_output": output,
        "llm_calls": llm.calls,
        "result": result,
        "elapsed": elapsed,
    }


def main() -> int:
    print("=" * 78)
    print("DIAGNOSTIC #3 — the full HITL round-trip (real agent + real runtime)")
    print("=" * 78)

    failures = 0

    for name, payload in ISSUE_PAYLOADS.items():
        out = run_case(name, payload)
        console_out = out["console_output"]
        norm_payload = _normalise(payload)

        print()
        print(f"--- payload: {name} " + "-" * (58 - len(name)))
        print(f"AgentQuestionEvent objects on the stream : {len(out['question_events'])}")
        for ev in out["question_events"]:
            print(f"    question_id={ev.question_id} input_type={ev.input_type!r} "
                  f"timeout={ev.timeout} question_len={len(ev.question)}")
        print(f"prompts handed to the console input module: {len(out['prompts'])}")
        for i, p in enumerate(out["prompts"], 1):
            print(f"    prompt #{i} ({len(p)} chars): {_normalise(p)[:110]!r}")
        shown_in_console = _normalise(console_out).count(norm_payload)
        shown_in_prompts = sum(_normalise(p).count(norm_payload) for p in out["prompts"])
        print(f"payload rendered by console.print        : {shown_in_console}")
        print(f"payload rendered by the input prompt     : {shown_in_prompts}")
        print(f"TOTAL renderings of the payload          : {shown_in_console + shown_in_prompts}")
        print(f"LLM calls                                : {len(out['llm_calls'])}")
        print(f"wall clock                               : {out['elapsed']:.3f}s")

        total = shown_in_console + shown_in_prompts
        if total > 1:
            print("  => VERDICT: the payload is rendered more than once.")
            failures += 1
        elif total == 0:
            print("  => VERDICT: the payload is never rendered — the operator is")
            print("     asked for a password instead of being asked the question.")
            failures += 1
        else:
            print("  => VERDICT: rendered once.")

        # Did the answer reach the agent?
        if out["llm_calls"]:
            last = " ".join(c for _, c in out["llm_calls"][-1])
            if "Human response" in last:
                print("  => the human's answer was fed back into the conversation.")
            else:
                print("  => WARNING: the human's answer never reached the agent.")

    print()
    print("=" * 78)
    if failures:
        print(f"RESULT: {failures} defect(s) reproduced end to end.")
        print("        The defects are CONFIRMED.")
    else:
        print("RESULT: no defect reproduced.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
