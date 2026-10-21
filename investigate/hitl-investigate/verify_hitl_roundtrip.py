"""
End-to-end verification of the Human-in-the-Loop round-trip.

This exercises the *real* production wiring:

  * ``components.hitl_agent.HITLFunctionAgent`` raises the question,
  * the framework publishes it to the workflow event stream,
  * ``components.event_consumer.EventConsumer`` prompts the user exactly once,
  * the answer is sent back and reaches the LLM,
  * the agent continues and produces a final answer.

Run from the repository root (self-development/):
    python investigate/hitl-investigate/verify_hitl_roundtrip.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, List, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

sys.path.insert(0, str(Path(__file__).resolve().parent))

from llama_index.core.base.llms.types import ChatMessage, ChatResponse
from llama_index.core.llms.callbacks import llm_chat_callback
from llama_index.core.llms.mock import MockFunctionCallingLLM
from llama_index.core.tools import FunctionTool
from pydantic import Field

from _hitl_test_doubles import add_two

from components.event_consumer import EventConsumer
from components.hitl_agent import HITLFunctionAgent
from components.hitl_events import AgentAnswerEvent, AgentQuestionEvent
from components.spinner_controller import SpinnerController
from components.state_handler import StateHandler
from rich.console import Console

RESULTS: List[tuple] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f"  — {detail}" if detail else ""))


QUESTION = "Shall I delete the database?"


class ScriptedLLM(MockFunctionCallingLLM):
    """Answers with a question first, then with a final message."""

    calls: List[Any] = Field(default_factory=list)

    @llm_chat_callback()
    async def astream_chat(self, messages: Sequence[ChatMessage], **kwargs: Any):
        self.calls.append([(m.role, str(m.content)) for m in messages])
        text = QUESTION if len(self.calls) == 1 else "Understood, I will not delete it."

        async def gen():
            yield ChatResponse(
                message=ChatMessage(role="assistant", content=text),
                delta=text,
                raw={"message": {"role": "assistant", "content": text}},
            )

        return gen()


class RecordingInput:
    """Stand-in for the console input module that records the prompts."""

    def __init__(self, answer: str = "no") -> None:
        self.answer = answer
        self.prompts: List[str] = []

    async def prompt(self, message: str = "", default: str = "", timeout: int = 30) -> str:
        self.prompts.append(message)
        return self.answer

    async def confirm(self, message: str = "", default_yes: bool = True, timeout: int = 30) -> bool:
        self.prompts.append(message)
        return self.answer.strip().lower() in ("y", "yes")


async def run_roundtrip(answer: str = "no", hitl_enabled: bool = True) -> dict:
    """Run one request through the real consumer + agent."""
    console = Console(force_terminal=False, width=80)
    spinner = SpinnerController(console=console)
    state = StateHandler()
    consumer = EventConsumer(
        spinner_controller=spinner,
        state_handler=state,
        console=console,
        hitl_timeout=5,
        hitl_default_answer="no",
        hitl_enabled=hitl_enabled,
    )
    recorder = RecordingInput(answer)
    consumer.console_input = recorder

    llm = ScriptedLLM()
    agent = HITLFunctionAgent(
        tools=[FunctionTool.from_defaults(fn=add_two)],
        llm=llm,
        hitl_enabled=hitl_enabled,
        hitl_default_timeout=5,
        hitl_default_answer="no",
    )

    handler = agent.run("delete the database")
    result = await consumer.consume_events(handler, "delete the database")

    return {
        "prompts": recorder.prompts,
        "llm_calls": llm.calls,
        "result": result,
        "consumer": consumer,
    }


async def main() -> int:
    print("=" * 78)
    print("HITL ROUND-TRIP VERIFICATION")
    print("=" * 78)

    # ------------------------------------------------------------------
    print("\n--- 1. A question produces exactly one prompt ---")
    out = await run_roundtrip(answer="no")
    check("1.1 user prompted exactly once", len(out["prompts"]) == 1,
          f"got {len(out['prompts'])}")
    check("1.2 the agent asked a second time (2 LLM calls)",
          len(out["llm_calls"]) == 2, f"got {len(out['llm_calls'])}")

    # ------------------------------------------------------------------
    print("\n--- 2. The answer reaches the LLM ---")
    last_call = out["llm_calls"][-1] if out["llm_calls"] else []
    joined = " ".join(content for _, content in last_call)
    check("2.1 the human's answer is in the next LLM call",
          "no" in joined and "Human response" in joined, joined[-120:])
    check("2.2 the final answer reflects the human's input",
          "not delete" in str(out["result"]).lower()
          or "will not" in str(out["result"]).lower(),
          str(out["result"])[:120])

    # ------------------------------------------------------------------
    print("\n--- 3. The question reaches the event stream ---")
    # The consumer's HITL counter only increments when the event arrived.
    stats = out["consumer"].get_hitl_stats()
    check("3.1 the consumer saw exactly one question",
          stats["question_count"] == 1, str(stats))

    # ------------------------------------------------------------------
    print("\n--- 4. HITL disabled -> no prompt, normal flow ---")
    out_disabled = await run_roundtrip(answer="no", hitl_enabled=False)
    check("4.1 no prompt when HITL is disabled",
          len(out_disabled["prompts"]) == 0,
          f"got {len(out_disabled['prompts'])}")
    check("4.2 the agent completed with a single LLM call",
          len(out_disabled["llm_calls"]) == 1,
          f"got {len(out_disabled['llm_calls'])}")

    # ------------------------------------------------------------------
    print("\n--- 5. The answer actually steers the agent ---")
    out_yes = await run_roundtrip(answer="yes, go ahead")
    joined_yes = " ".join(c for _, c in (out_yes["llm_calls"][-1] if out_yes["llm_calls"] else []))
    check("5.1 the affirmative answer reached the LLM",
          "yes, go ahead" in joined_yes, joined_yes[-120:])

    print("\n" + "=" * 78)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print(f"RESULT: {passed}/{total} checks passed")
    for name, ok, detail in RESULTS:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    print("=" * 78)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
