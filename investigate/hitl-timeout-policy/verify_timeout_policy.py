"""Verify the timeout policy the operator stated.

The policy, in their words:

    "if timeout is -1 you have to stop and wait; if timeout is set you
     have to wait and the timeout expires, you can act on your own
     judgement."

Every check below runs the **real** stack: the real
:class:`HITLFunctionAgent`, the real :class:`EventConsumer`, the real
:class:`ConsoleInputModule`.  Only the *human* is a double: the builtin
``input`` is replaced by a function that answers late, or never.

Run from the repository root::

    .venv/bin/python investigate/hitl-timeout-policy/verify_timeout_policy.py
"""
from __future__ import annotations

import asyncio
import builtins
import os
import sys
import time
from typing import Any, List, Optional, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
))))

from llama_index.core.base.llms.types import ChatMessage, ChatResponse
from llama_index.core.llms.callbacks import llm_chat_callback
from llama_index.core.llms.mock import MockFunctionCallingLLM
from llama_index.core.tools import FunctionTool
from pydantic import Field
from rich.console import Console

from components.console_input_module import ConsoleInputModule
from components.event_consumer import EventConsumer
from components.hitl_agent import HITLFunctionAgent
from components.human_loop_handler import HumanLoopHandler
from components.spinner_controller import SpinnerController
from components.state_handler import StateHandler

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"

results: List[tuple[str, bool, str]] = []

QUESTION = "Which one should I use?"
FINAL = "Understood, I will take the first option."


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, condition, detail))
    print(f"[{PASS if condition else FAIL}] {name}" + (f" — {detail}" if detail else ""))


def add_two(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


class QuestionLLM(MockFunctionCallingLLM):
    """Asks the question first, then answers with a final message.

    The second call is the interesting one: the messages it receives are
    what the model was told about the human's answer.
    """

    calls: List[Any] = Field(default_factory=list)
    question: str = QUESTION

    @llm_chat_callback()
    async def astream_chat(self, messages: Sequence[ChatMessage], **kwargs: Any):
        self.calls.append([(m.role, str(m.content)) for m in messages])
        text = self.question if len(self.calls) == 1 else FINAL

        async def gen():
            yield ChatResponse(
                message=ChatMessage(role="assistant", content=text),
                delta=text,
                raw={"message": {"role": "assistant", "content": text}},
            )

        return gen()


class Human:
    """The human at the keyboard.

    ``delay`` is how long they take to answer; ``None`` means they never
    answer at all.
    """

    def __init__(self, delay: Optional[float], answer: str = "2") -> None:
        self.delay = delay
        self.answer = answer
        self.prompts: List[str] = []

    def input(self, message: str = "") -> str:
        self.prompts.append(message)
        if self.delay is None:
            time.sleep(30)  # the human walks away
        time.sleep(self.delay)
        return self.answer


async def run_stack(
    timeout: int,
    human: Human,
    default_answer: str = "1",
    wait_for: Optional[float] = None,
    question: str = QUESTION,
) -> dict:
    """Run one request through the real agent + consumer + input module.

    Returns the LLM calls, the human's prompts and the timeout log.  When
    *wait_for* is given the run is abandoned after that many seconds — used
    to prove that the agent is still waiting.
    """
    handler = HumanLoopHandler(enable_hitl=True, default_timeout=timeout)
    console = Console(force_terminal=False, width=80)
    consumer = EventConsumer(
        spinner_controller=SpinnerController(console=console),
        state_handler=StateHandler(),
        console=console,
        hitl_timeout=timeout,
        hitl_default_answer=default_answer,
        hitl_enabled=True,
        human_loop_handler=handler,
    )

    llm = QuestionLLM(question=question)
    agent = HITLFunctionAgent(
        tools=[FunctionTool.from_defaults(fn=add_two)],
        llm=llm,
        hitl_enabled=True,
        hitl_default_timeout=timeout,
        hitl_default_answer=default_answer,
    )

    original_input = builtins.input
    builtins.input = human.input
    try:
        workflow = agent.run("pick one")
        coro = consumer.consume_events(workflow, "pick one")
        if wait_for is None:
            await coro
            completed = True
        else:
            try:
                await asyncio.wait_for(coro, timeout=wait_for)
                completed = True
            except asyncio.TimeoutError:
                completed = False
    finally:
        builtins.input = original_input

    return {
        "completed": completed,
        "llm_calls": llm.calls,
        "prompts": human.prompts,
        "timeout_log": handler.get_timeout_log(),
        "history": handler.get_question_history(),
    }


async def main() -> int:
    print("=" * 78)
    print("HITL timeout policy — the operator's rule, against the real stack")
    print("=" * 78)

    # ------------------------------------------------------------------
    # R1: timeout = -1 -> stop and wait
    # ------------------------------------------------------------------
    print("\n-- R1: timeout = -1 (no timeout): the agent must wait --\n")

    late = Human(delay=1.2, answer="2")
    out = await run_stack(timeout=-1, human=late)
    check(
        "R1a a slow human is still waited for (no timeout)",
        out["completed"] and len(out["llm_calls"]) >= 2,
        f"llm calls={len(out['llm_calls'])}, prompts={out['prompts']}",
    )
    told = " ".join(
        content for role, content in (out["llm_calls"][-1] if out["llm_calls"] else [])
    )
    check(
        "R1b the human's own answer reaches the model",
        "2" in told,
        f"model saw: {told[-120:]!r}",
    )

    silent = Human(delay=None)
    out = await run_stack(timeout=-1, human=silent, wait_for=2.5)
    check(
        "R1c a silent human makes the agent wait (it does not decide on its own)",
        not out["completed"],
        f"completed={out['completed']}",
    )
    check(
        "R1d no answer was recorded while the agent was waiting",
        not out["timeout_log"],
        f"timeout log={out['timeout_log']}",
    )

    # ------------------------------------------------------------------
    # R2: timeout = N -> wait, then act on your own judgement
    # ------------------------------------------------------------------
    print("\n-- R2: timeout = 1s: the agent waits, then decides on its own --\n")

    slow = Human(delay=5.0, answer="2")
    started = time.monotonic()
    out = await run_stack(timeout=1, human=slow, default_answer="1")
    elapsed = time.monotonic() - started

    check(
        "R2a the run continues after the timeout expires",
        out["completed"] and len(out["llm_calls"]) >= 2,
        f"completed={out['completed']}, llm calls={len(out['llm_calls'])}",
    )
    check(
        "R2b the agent did not wait for the slow human",
        elapsed < 4.0,
        f"finished after {elapsed:.1f}s (the human needed 5s)",
    )
    check(
        "R2c the timeout is recorded",
        bool(out["timeout_log"]),
        f"timeout log={out['timeout_log']}",
    )
    check(
        "R2d the fallback answer was used",
        any(
            entry.get("default_answer") == "1"
            for entry in out["timeout_log"]
        ),
        f"default_answer={[e.get('default_answer') for e in out['timeout_log']]}",
    )

    told = " ".join(
        content for role, content in (out["llm_calls"][-1] if out["llm_calls"] else [])
    )
    print(f"\n  the model was told: {told[-200:]!r}")
    check(
        "R2e the model is told the human did not answer",
        "no human response" in told.lower() and "own judgement" in told.lower(),
        f"the model was told: {told[-120:]!r}",
    )

    # ------------------------------------------------------------------
    # R3: the shipped default — an empty fallback answer
    # ------------------------------------------------------------------
    print("\n-- R3: timeout = 1s, the shipped default (no fallback answer) --\n")

    slow = Human(delay=5.0, answer="y")
    out = await run_stack(
        timeout=1,
        human=slow,
        default_answer="",
        question="Shall I delete the database?",
    )
    told = " ".join(
        content for role, content in (out["llm_calls"][-1] if out["llm_calls"] else [])
    )
    print(f"  the model was told: {told[-200:]!r}")
    check(
        "R3a the run continues (the agent decides on its own)",
        out["completed"] and len(out["llm_calls"]) >= 2,
        f"completed={out['completed']}",
    )
    check(
        "R3b the model can tell that nobody answered",
        "no human response" in told.lower() and "own judgement" in told.lower(),
        f"the model was told: {told[-120:]!r}",
    )

    # ------------------------------------------------------------------
    print("\n" + "=" * 78)
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"{passed}/{len(results)} checks pass")
    print("=" * 78)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    _code = asyncio.run(main())
    # The human threads sleep in an executor that cannot be cancelled; the
    # process must not wait for them.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_code)
